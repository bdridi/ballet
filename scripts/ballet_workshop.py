"""Le Conductor du Workshop en autopilot : l'état d'une session de Workshop, ses transitions, et chaque action qu'elles déclenchent.

    python3 ballet_workshop.py begin   [<élément>]                      # ouvre la session de l'élément : le Dramaturg le cadre
    python3 ballet_workshop.py begin   --request "<demande>"            # une demande hors backlog : le Dramaturg la capture, puis la cadre
    python3 ballet_workshop.py receive [<élément>] --message <msg-id>   # un message du Dramaturg, lu chez Orca par son id
    python3 ballet_workshop.py receive [<élément>] --dispatch <ctx-id>  # le dernier message du worker de ce dispatch
    python3 ballet_workshop.py resume  [<élément>]                      # reprend ce qu'une escalade a arrêté
    python3 ballet_workshop.py status  [<élément>]                      # où en est la session

Lancé depuis le home du projet, comme `ballet_rehearsal.py`, avec la même dernière ligne :
    NEXT: wait               le Dramaturg travaille ; Orca réveillera le Conductor
    NEXT: escalate <motif>   le Director décide ; la session attend
    NEXT: done               l'issue est publiée : la session est finie

Un élément confié est une ligne du backlog des specs (`OPP-12`, `FEAT-007`, `BUG-004`, `TASK-009`). Sa session vit dans
`.ballet/run/workshop-<élément>.json` (jamais `session-…` : ce sont celles de la Rehearsal) ; ses lignes de journal portent
la clé `workshop`. Une session par élément ; plusieurs côte à côte sont permises.

Le déroulé, sans le Director : le Dramaturg cadre l'élément dans un worktree sur `workshop/<élément>` et rend son rapport
(le type de l'issue, ce qu'il a décidé seul, le brouillon de l'issue). Le script juge alors son passage (la politique : seul
l'espace specs a bougé), pousse la branche, ouvre la PR des specs et la merge aussitôt (le Workshop n'a ni Critic ni CI : `merge-specs`), puis publie l'issue, et la range. Son `Ballet status` est `proposed` (le Director l'accepte avant
qu'elle entre dans la file), ou `ready` pour les types de `[workshop] queue_approval_skipped`. Rien n'est écrit sur `main`
que par ce merge. Personne ne répond à une question dans cette boucle : le Dramaturg décide dans son périmètre, ou dit
qu'il est bloqué (`- Blocked: <motif>`), et le Director en est prévenu.

Une seule exception : le Dramaturg peut consulter le Choreographer (une question `to: choreographer`). À la première question,
le script lance le Choreographer en worker dans le même worktree ; aux suivantes, il la lui envoie dans sa session. Il ne le
laisse rien écrire (la politique le juge comme le Critic) et rend chaque réponse au Dramaturg. Le nombre de tours n'a qu'une
borne, `[escalation] max_exchange_rounds` (le profil du projet l'emporte sur celui du plugin) : la question d'au-delà escalade.
Comme en Rehearsal, chaque message réveille le Conductor, qui lance `receive` ; le script relaie, journalise, et publie chaque
question et chaque réponse en commentaire sur l'issue dès qu'elle existe (elle naît à la fin du Workshop).

Une demande qui n'est pas encore au backlog (`--request`) nomme sa session d'un slug, ses premiers mots sans accents
(`le-stock-passe-en-negatif`) : branche `workshop/<slug>`, état `workshop-<slug>.json`. Le Dramaturg la capture d'abord
(une ligne nouvelle, ou fusionnée dans une ligne existante), puis cadre cette ligne, qu'il nomme dans son rapport (`- Item:`).

Le journal ne se réécrit jamais : la clé d'une session reste son élément (`BUG-004`) ou son slug du début à la fin, et l'événement
`published` fait le lien avec la ligne du backlog et l'issue nées en chemin (`{"item": "BUG-004", "issue": "21", …}`), comme `handover` relie une
planification à sa slice en Rehearsal : la Scène suit `BUG-004` → `#21` → la Rehearsal de `#21`.

Ce que le Dramaturg décide seul (`## Decided alone`) est écrit dans l'issue, qui porte alors le libellé `ballet:decided-alone`.

Comme en Rehearsal, une transition qui finit en `NEXT: escalate` ou `NEXT: done` est annoncée à Maestro (`ballet_maestro.announce`).

Sans élément, `begin` choisit dans le backlog : la première ligne de *Next up* (OPP, FEAT, BUG ou TASK) qui n'a pas encore sa
session. Ce que le Workshop choisit seul sort toujours `proposed`, quel que soit `queue_approval_skipped`.
"""

import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import ballet_config
import ballet_github
import ballet_maestro
import ballet_orca
import ballet_policy
import ballet_rehearsal
from ballet_message import MessageError, parse_message
from ballet_rehearsal import RehearsalError, Step, Tools, UsageError

RUN_DIR = ballet_rehearsal.RUN_DIR
WORKSHOP_PREFIX = "workshop-"
WORKSHOP_ITEM = re.compile(r"^(?:OPP|FEAT|BUG|TASK)-\d+$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLUG_WORDS = 6
ISSUE_DRAFT_HEADING = "## Issue draft"
DECIDED_HEADING = "## Decided alone"
NEXT_UP_HEADING = "## Next up"
NEXT_UP_LINE = re.compile(r"^\s*(?:\d+\.|[-*])\s+\W*((?:OPP|FEAT|BUG|TASK)-\d+)\b", re.MULTILINE)
PROPOSED, READY = "proposed", "ready"
MAX_NUDGES = 1
MAX_REFUSED_REPORTS = 1
CAPTURE = """The Director's request, not in the backlog yet: "{request}"

Capture it first (the skill's *Capture*, no question): a new line, or a merge into an existing line, committed on this branch. The line it lands on is the item you frame below. Your report then starts with `- Item: <its ID>` (`OPP-N`, `FEAT-N`, `BUG-N` or `TASK-N`). Already covered by a feature, or to reject: write nothing and report `- Blocked: <why>`.

"""
FRAMING = """Frame {item}, a line of the backlog: make it one ready feature (or, for a bug or a task, the line that reaches the top of *Next up*) in the specs space, committed on this branch with the skill's commit messages. Write no plan and no code. Do not publish the issue: the script does, once your specs are on `main`.

Your report (a Ballet message, `type: report`, `from: dramaturg`, `to: conductor`, subject `{subject}`) holds, in this order:
- `- Type: Feature`, `- Type: Bug` or `- Type: Task`: the type of the issue to publish;
- `## Decided alone`: one line per business decision you made without the Director, with your reason (the issue carries them and the Director reads them to accept the proposal); leave the section out when you decided nothing;
- `## Issue draft`: always the last section, the issue body to its end, from the template `issue.md` without its plan, its first line the title `# FEAT-NNN · <name>` (`BUG-NNN`, `TASK-NNN`).

A feature that touches a technical choice (a new dependency, a data model, a contract other code relies on, several repos, its size): ask the Choreographer before you write, with a message `type: question`, `to: choreographer`, `round` 1 then + 1 at each new question, numbered points each with your recommendation, as your `worker_done`, the worktree clean. Its answer comes back to you; ask again while a point stays open, up to {rounds} round(s) (`[escalation] max_exchange_rounds`): beyond, the Director decides. What it changes in the product, you decide.

When the item cannot be framed (it is not in the backlog, there is nothing to build, only the Director can settle a question), write nothing and report `- Blocked: <why>`, nothing else."""


class WorkshopError(Exception):
    """Le Workshop ne peut pas avancer : le Conductor escalade."""


ERRORS = (WorkshopError, RehearsalError, ballet_github.GitHubError)   # `Tools.run` lève une RehearsalError


@dataclass
class Workshop:
    """Une session de Workshop : un élément du backlog, son worktree, son Dramaturg, et jusqu'où ses specs et son issue sont allées."""
    item: str                                   # `OPP-12`, `FEAT-007`, `BUG-004`, `TASK-009`, ou le slug d'une demande
    repo: str
    worktree: str = ""
    dispatch: str = ""                          # le dispatch Orca du worker Dramaturg
    status: str = "open"                        # open | escalated | done
    reason: str = ""                            # le motif de la dernière escalade, ou de la fin
    checkpoint: str = ""                        # `HEAD` du worktree quand le Dramaturg a reçu la main
    refs: list = field(default_factory=list)    # branches et tags à ce moment
    nudges: int = 0                             # relances sans `worker_done`, remises à zéro à son prochain message
    violations: int = 0                         # passages du Dramaturg refusés par la politique
    refused_reports: int = 0                    # rapports renvoyés au Dramaturg : sans type valide ou sans brouillon
    report: str = ""                            # son rapport, gardé pour reprendre après une escalade
    pull_request: str = ""                      # la PR de ses specs
    merged: bool = False                        # ses specs sont sur `main` (ou il n'y en avait pas)
    issue: str = ""                             # l'issue publiée
    ballet_status: str = ""                     # son statut à la publication : `proposed` ou `ready`
    picked: bool = False                        # l'élément a été choisi par le Workshop dans le backlog : toujours `proposed`
    request: str = ""                           # la demande hors backlog que la session porte sous son slug
    framed: str = ""                            # la ligne du backlog où le Dramaturg l'a capturée (`- Item:`)
    marked: bool = False                        # l'issue porte `ballet:decided-alone` (ou n'en a pas besoin)
    question: str = ""                          # la question du Dramaturg au Choreographer, tant qu'elle n'a pas de réponse
    rounds: int = 0                             # questions du Dramaturg au Choreographer, bornées par `max_exchange_rounds`
    advisor_dispatch: str = ""                  # le dispatch Orca du worker Choreographer
    advisor_checkpoint: str = ""                # `HEAD` du worktree quand le Choreographer a reçu la main
    received: list = field(default_factory=list)  # les ids des messages Orca déjà traités : `receive --run` ne les rejoue pas
    advisor_refs: list = field(default_factory=list)
    advice: str = ""                            # sa dernière réponse
    exchanges: list = field(default_factory=list)   # les questions et réponses, messages entiers, dans l'ordre
    exchanges_published: int = 0                # combien sont déjà commentées sur l'issue

    @property
    def branch(self):
        return f"workshop/{self.item}"


@dataclass
class Report:
    """Ce que le script lit dans le rapport du Dramaturg."""
    issue_type: str
    draft: str
    decided: list                               # les lignes de `## Decided alone`
    item: str = ""                              # `- Item:`, la ligne où une demande a été capturée


# --- les entrées du Conductor -------------------------------------------------


def begin(item, home, tools, request=""):
    """Ouvre la session de l'élément : un worktree sur `workshop/<élément>`, depuis `main`, et le Dramaturg qui le cadre.
    Une demande hors backlog nomme la session de son slug ; sans élément ni demande, le Workshop choisit lui-même dans le backlog."""
    config = _checked_config(home)
    picked = not item and not request
    item = item or (_free_slug(request, home) if request else _pick_in_backlog(config, home))
    _refuse_if_open(item, home)
    workshop = Workshop(item=item, repo=_repo(config, home), picked=picked, request=request)
    workshop.worktree = _open_worktree(workshop, tools)
    git = tools.git(workshop.worktree)
    workshop.checkpoint, workshop.refs = ballet_policy.head(git), ballet_policy.refs(git)
    _log(home, workshop, "begin", {"item": item, "picked": picked, "request": request})
    step = Step("wait", done=[f"worktree {workshop.worktree} on {workshop.branch}, from origin/main"])
    return _settle(workshop, _start_dramaturg(workshop, step, config, home, tools), home)


def receive_from_orca(item, wanted, home, tools, by="message"):
    """Le message d'un worker, lu chez Orca par son id (`by="message"`) ou comme le dernier de son dispatch
    (`by="dispatch"`) : le Conductor ne le recopie pas."""
    config = _checked_config(home)
    workshop = _load(item, home)
    if workshop.status == "done":
        return _over(workshop)
    try:
        message = _orca_message(wanted, by, tools)
    except ERRORS as error:
        return _settle(workshop, Step("escalate", str(error)), home)
    return _settle(workshop, _received_step(workshop, message, config, home, tools), home)


def receive_from_run(item, run_id, home, tools):
    """Le réveil qui ne nomme que le Run du Conductor : ses messages en attente sont consommés d'un coup ; ceux des
    workers du Workshop, pas encore traités, avancent dans l'ordre, chacun comme par `--message`, jusqu'au premier pas
    qui n'est pas `wait`. Les autres sont ignorés."""
    config = _checked_config(home)
    workshop = _load(item, home)
    if workshop.status == "done":
        return _over(workshop)
    batch = ballet_orca.run_messages(run_id, tools)
    mine = [message for message in batch if _is_new_for(workshop, message)]
    ignored = len(batch) - len(mine)
    if not mine:
        return _nothing_new(workshop, run_id, ignored)
    steps = []
    for message in mine:
        steps.append(_settle(workshop, _received_step(workshop, message, config, home, tools), home))
        if steps[-1].next != "wait" or workshop.status != "open":
            break
    return _merged_steps(workshop, steps, mine[len(steps):], ignored)


def resume(item, home, tools):
    """Reprend ce qu'une escalade a arrêté : le Dramaturg qui n'a pas pu démarrer, ou la fin qui a échoué (le merge, la publication)."""
    config = _checked_config(home)
    workshop = _load(item, home)
    if workshop.status == "done":
        return _over(workshop)
    try:
        step = _resumed(workshop, config, home, tools)
    except ERRORS as error:
        step = Step("escalate", str(error))
    return _settle(workshop, step, home)


def status(item, home, tools):
    """Où en est la session, en clair : sa dernière ligne `NEXT` est celle du dernier pas."""
    workshop = _load(item, home)
    lines = [f"Workshop {workshop.item}: {workshop.status}", f"branch {workshop.branch}, worktree {workshop.worktree}"]
    lines += [f"request: {workshop.request}" + (f", captured as {workshop.framed}" if workshop.framed else "")] if workshop.request else []
    lines += [f"dramaturg: dispatch {workshop.dispatch or 'not started'}{', picked in the backlog' if workshop.picked else ''}"]
    lines += [f"choreographer: dispatch {workshop.advisor_dispatch or 'not started'}, round {workshop.rounds}, {'waiting for its answer' if workshop.question else 'answered'}"] if workshop.rounds else []
    lines += [f"specs: pull request #{workshop.pull_request}{', merged' if workshop.merged else ''}"] if workshop.pull_request else []
    lines += [f"issue #{workshop.issue}, Ballet status {workshop.ballet_status}{', decided alone' if workshop.marked else ''}"] if workshop.issue else []
    return Step(ballet_rehearsal.STEP_OF_STATUS[workshop.status], workshop.reason, lines)


# --- le Dramaturg -------------------------------------------------------------


def _start_dramaturg(workshop, step, config, home, tools):
    try:
        framing = _framing(workshop, config)
        workshop.dispatch = _start_worker(workshop, "dramaturg", _role_spec(workshop, framing), framing, config, home, tools)
    except ERRORS as error:
        return Step("escalate", f"the dramaturg could not start: {error}", step.done)
    return Step("wait", done=step.done + [f"dramaturg started on {workshop.item}"])


def _ask_advisor(workshop, config, home, tools):
    """La question va au Choreographer : lancé à la première, dans sa session ensuite. Le point de contrôle est pris à chaque
    question : le Dramaturg a pu commiter entre deux tours."""
    git = tools.git(workshop.worktree)
    workshop.advisor_checkpoint, workshop.advisor_refs = ballet_policy.head(git), ballet_policy.refs(git)
    if not workshop.advisor_dispatch:
        return _start_advisor(workshop, Step("wait"), config, home, tools)
    _send(workshop, "choreographer", f"{workshop.item} · dramaturg's question, round {workshop.rounds}", workshop.question, "send", home, tools)
    return Step("wait", done=[f"the dramaturg asked the choreographer again (round {workshop.rounds}): sent to its session"])


def _start_advisor(workshop, step, config, home, tools):
    """Le Choreographer répond à la question du Dramaturg, dans le même worktree, sans rien y écrire."""
    try:
        workshop.advisor_dispatch = _start_worker(workshop, "choreographer", _advisor_spec(workshop), workshop.question, config, home, tools)
    except ERRORS as error:
        return Step("escalate", f"the choreographer could not start: {error}", step.done)
    return Step("wait", done=step.done + [f"the dramaturg asked the choreographer: choreographer started on {workshop.item}"])


def _start_worker(workshop, role, mission, brief, config, home, tools):
    """Lance le worker du rôle dans le worktree du Workshop, journalise sa mission et rend son dispatch."""
    route = config["roles"][role]
    agent = ballet_rehearsal.ORCA_AGENTS.get(route.get("cli"))
    if not agent:
        raise WorkshopError(f"the {role}'s CLI `{route.get('cli')}` cannot run as an Orca worker yet")
    spec = _folder(workshop, home) / f"{role}-1.md"
    spec.write_text(mission, encoding="utf-8")
    dispatch = ballet_orca.start_worker(spec, workshop.worktree, agent, f"{role.capitalize()} · {workshop.item}", tools,
                                        model=route.get("model", ""))
    if not dispatch:
        raise WorkshopError("the worker started but its receipt names no dispatchId")
    _log(home, workshop, "handoff", {"role": role, "dispatch": dispatch, "how": "start", "agent": agent,
                                     "model": route.get("model", ""), "text": brief})
    return dispatch


def _framing(workshop, config):
    rounds = config["escalation"]["max_exchange_rounds"]
    if not workshop.request:
        return FRAMING.format(item=workshop.item, subject=workshop.item, rounds=rounds)
    return CAPTURE.format(request=workshop.request) + FRAMING.format(item="the line you captured", subject=workshop.item, rounds=rounds)


def _role_spec(workshop, framing):
    return f"""You are the Ballet Dramaturg of the autopilot Workshop on {workshop.item}, branch `{workshop.branch}`, in this worktree.

Load the skill `/ballet:dramaturg` and follow its section *In an autopilot Workshop*.

{framing}

Under the Conductor:
- Nobody answers a question in this Workshop, except the Choreographer above: never ask anyone else. Decide within your perimeter, and write what you decided.
- When you are done: send your `worker_done`, whose body is your final message, whole, header line first. Ending your turn without sending it stops the Workshop.
- Never push, never run `gh`, never change branch.
"""


def _advisor_spec(workshop):
    return f"""You are the Ballet Choreographer, consulted by the Dramaturg of the autopilot Workshop on {workshop.item}, in its worktree (branch `{workshop.branch}`).

Load the skill `/ballet:choreographer` and follow its section *When consulted during a Workshop*. The Dramaturg's question:

{workshop.question}

Under the Conductor:
- Write nothing: no file, no commit, no plan, no ADR, no `gh`. Read the specs and the code only; the policy checks that the worktree and its branch are as you found them.
- Answer with a Ballet message (`templates/message.md`) `type: answer`, `from: choreographer`, `to: dramaturg`, subject `{workshop.item}`, round as in the question, one line per point, by number.
- When you are done: send your `worker_done`, whose body is your answer, whole, header line first. Ending your turn without sending it stops the Workshop.
- The Dramaturg may ask again: its next question reaches you in this session; answer it the same way.
"""


def _handle_worker_message(workshop, message, config, home, tools):
    if message.get("type") == "escalation":
        return _worker_stopped(workshop, message, home, tools)
    header, text = _parsed(message.get("body", ""))
    _log(home, workshop, "message", {**header, "text": text})
    workshop.nudges = 0
    return _route(workshop, header, text, config, home, tools)


def _route(workshop, header, text, config, home, tools):
    sender, kind = header["from"], header["type"]
    if sender == "choreographer":
        return _after_advice(workshop, header, text, config, home, tools)
    if sender != "dramaturg":
        raise WorkshopError(f"a message from the {sender}: only the dramaturg and the choreographer it consults play in this Workshop")
    if kind == "report":
        return _after_report(workshop, text, config, home, tools)
    if kind == "question":
        return _after_question(workshop, header, text, config, home, tools)
    if kind == "escalation":
        return Step("escalate", "the dramaturg escalates: see its message")
    raise WorkshopError(f"no transition for a {kind} from the dramaturg")


def _worker_stopped(workshop, message, home, tools):
    """Un worker a fini son tour sans `worker_done` : relancé pour envoyer son message, une fois ; ensuite, ou
    s'il est tombé en erreur, c'est au Director."""
    payload = ballet_orca.payload(message)
    role = _role_of(workshop, payload.get("dispatchId"))
    if not role or payload.get("stopReason") != "finished" or workshop.nudges >= MAX_NUDGES:
        raise WorkshopError(f"Orca: {message.get('subject', 'a worker stopped')}: {message.get('body', '')[:300]}")
    workshop.nudges += 1
    _send(workshop, role, f"{workshop.item} · {role}: send your worker_done", ballet_rehearsal.REPORT_REMINDER, "nudge", home, tools)
    return Step("wait", done=[f"the {role} ended its turn without worker_done: asked to send its message"])


def _role_of(workshop, dispatch):
    if dispatch and dispatch == workshop.dispatch:
        return "dramaturg"
    if dispatch and dispatch == workshop.advisor_dispatch:
        return "choreographer"
    return None


def _send(workshop, role, subject, body, how, home, tools):
    dispatch = workshop.advisor_dispatch if role == "choreographer" else workshop.dispatch
    tools.orca(["orchestration", "send", "--to", f"dispatch:{dispatch}", "--subject", subject, "--body", body])
    _log(home, workshop, "handoff", {"role": role, "dispatch": dispatch, "how": how, "text": body})


# --- la consultation du Choreographer -----------------------------------------


def _after_question(workshop, header, text, config, home, tools):
    """Le Dramaturg ne peut consulter que le Choreographer, autant de tours que `max_exchange_rounds` en permet ; le script
    compte les tours lui-même, sans se fier à l'en-tête. Toute autre question va au Director."""
    if header["to"] != "choreographer":
        return Step("escalate", f"the dramaturg asks the {header['to']}, and nobody answers in an autopilot Workshop: see its message")
    limit = config["escalation"]["max_exchange_rounds"]
    if workshop.rounds >= limit:
        return Step("escalate", f"round {workshop.rounds + 1} on {workshop.item} between dramaturg and choreographer, over max_exchange_rounds ({limit}): see its message")
    workshop.rounds, workshop.question = workshop.rounds + 1, text
    workshop.exchanges.append(text)
    return _ask_advisor(workshop, config, home, tools)


def _after_advice(workshop, header, text, config, home, tools):
    """La réponse du Choreographer, si la politique la laisse passer (il n'a rien écrit), va au Dramaturg."""
    if header["type"] != "answer" or header["to"] != "dramaturg" or not workshop.question:
        raise WorkshopError(f"a {header['type']} to the {header['to']} from the choreographer: it only answers the dramaturg's questions")
    found = _advisor_policy(workshop, config, home, tools)
    if found:
        return Step("escalate", f"policy: the choreographer broke the rules: {'; '.join(found)}")
    workshop.advice, workshop.question = text, ""
    workshop.exchanges.append(text)
    _send(workshop, "dramaturg", f"{workshop.item} · choreographer's answer", text, "send", home, tools)
    return Step("wait", done=["the choreographer answered: its answer was sent to the dramaturg"])


def _advisor_policy(workshop, config, home, tools):
    """Le Choreographer consulté est jugé comme le Critic : il ne change ni le worktree, ni la branche, ni `HEAD`."""
    passage = ballet_policy.Passage("critic", workshop.branch, workshop.advisor_checkpoint, workshop.advisor_refs)
    found = ballet_policy.violations(passage, ballet_policy.policy_of(config), tools.git(workshop.worktree))
    _log(home, workshop, "policy", {"role": "choreographer", "violations": found})
    return found


# --- après son rapport --------------------------------------------------------


def _after_report(workshop, text, config, home, tools):
    blocked = _report_field(text, "Blocked")
    if blocked:
        return Step("escalate", f"the dramaturg is blocked: {blocked}")
    try:
        _read_report(text, needs_item=bool(workshop.request))
    except WorkshopError as error:
        return _refused_report(workshop, error, home, tools)
    workshop.report = text
    return _finish(workshop, Step("wait"), config, home, tools)


def _refused_report(workshop, error, home, tools):
    """Un rapport sans type valide ou sans brouillon est renvoyé une fois au Dramaturg ; la deuxième fois, le Director décide."""
    workshop.refused_reports += 1
    if workshop.refused_reports > MAX_REFUSED_REPORTS:
        return Step("escalate", str(error))
    _send(workshop, "dramaturg", f"{workshop.item} · dramaturg: complete your report", f"Your report is refused: {error}. Report again, whole.", "send", home, tools)
    return Step("wait", done=[f"report refused ({error}): sent back to the dramaturg"])


def _resumed(workshop, config, home, tools):
    if not workshop.dispatch:
        return _start_dramaturg(workshop, Step("wait"), config, home, tools)
    if workshop.question and not workshop.advisor_dispatch:
        return _start_advisor(workshop, Step("wait"), config, home, tools)
    if workshop.report:
        return _finish(workshop, Step("wait"), config, home, tools)
    return Step(ballet_rehearsal.STEP_OF_STATUS[workshop.status], workshop.reason, ["nothing to resume: the dramaturg has not reported yet"])


def _finish(workshop, step, config, home, tools):
    """La politique juge le passage, les specs vont sur `main`, l'issue est publiée, le worktree est rangé. Chaque étape
    faite est retenue : une reprise après un échec repart de celle qui a échoué."""
    report = _read_report(workshop.report, needs_item=bool(workshop.request))
    workshop.framed = report.item
    if not workshop.merged:
        found = _policy(workshop, config, home, tools)
        if found:
            return _refused_by_policy(workshop, found, step, home, tools)
        step.done += _specs_to_main(workshop, tools)
    step.done += _publish_issue(workshop, report, config, home, tools)
    step.done += _mark_decided_alone(workshop, report, tools)
    step.done += _publish_exchanges(workshop, home, tools)
    tools.orca(["worktree", "rm", "--worktree", f"path:{workshop.worktree}", "--delete-branch"])
    step.done.append("worktree removed")
    return Step("done", f"{workshop.item}: issue #{workshop.issue} published as {workshop.ballet_status}", step.done)


def _policy(workshop, config, home, tools):
    """Les violations du passage du Dramaturg, journalisées à chaque fois : seul l'espace specs a le droit de bouger."""
    passage = ballet_policy.Passage("dramaturg", workshop.branch, workshop.checkpoint, workshop.refs)
    found = ballet_policy.violations(passage, ballet_policy.policy_of(config), tools.git(workshop.worktree))
    _log(home, workshop, "policy", {"role": "dramaturg", "violations": found})
    return found


def _refused_by_policy(workshop, found, step, home, tools):
    """Le Dramaturg corrige une fois, avec de nouveaux commits (le point de contrôle ne bouge pas : un revert suffit) ;
    la deuxième violation escalade."""
    workshop.violations += 1
    listed = "; ".join(found)
    if workshop.violations > ballet_rehearsal.MAX_POLICY_RESENDS:
        return Step("escalate", f"policy: the dramaturg broke the rules: {listed}", step.done)
    workshop.report = ""
    _send(workshop, "dramaturg", f"{workshop.item} · dramaturg: fix your passage", _policy_fix_assignment(found), "send", home, tools)
    return Step("wait", done=step.done + [f"policy refused the dramaturg ({listed}): sent back to fix it"])


def _policy_fix_assignment(found):
    listed = "\n".join(f"- {violation}" for violation in found)
    return (f"Ballet's policy refused your work: nothing was pushed.\n\n{listed}\n\nFix it with new commits (a revert is "
            "fine), never by rewriting history, and leave the worktree clean. Then report again. A second violation goes to the Director.")


def _specs_to_main(workshop, tools):
    """Les specs du Dramaturg arrivent sur `main` par une PR, mergée aussitôt (ni Critic ni CI) ; sans commit, rien à merger."""
    if not ballet_policy.commits_since(workshop.checkpoint, tools.git(workshop.worktree)):
        workshop.merged = True
        return ["no specs written: nothing to merge"]
    lines = _open_specs_pull_request(workshop, tools)
    ballet_github.merge_specs_pull_request(workshop.pull_request, run=tools.gh, git=tools.git(workshop.repo))
    workshop.merged = True
    return lines + [f"#{workshop.pull_request} merged by rebase, {workshop.branch} deleted"]


def _open_specs_pull_request(workshop, tools):
    if workshop.pull_request:
        return []
    ballet_github.push_branch(workshop.branch, git=tools.git(workshop.repo))
    workshop.pull_request = ballet_github.open_specs_pull_request(workshop.branch, run=tools.gh)
    return [f"{workshop.branch} pushed", f"pull request #{workshop.pull_request} opened"]


def _publish_issue(workshop, report, config, home, tools):
    """L'issue du Workshop, publiée par le script : `proposed`, ou `ready` pour un type que le Director a dispensé de son oui
    (jamais pour un élément que le Workshop a choisi seul). Ses liens « blocked by » (ligne `Depends on:` du brouillon) sont posés
    par la publication ; les dépendances se cherchent dans les specs du worktree du Dramaturg. Rend la ligne de l'étape, puis
    une ligne par lien."""
    if workshop.issue:
        return [f"issue #{workshop.issue} already published as {workshop.ballet_status}"]
    skipped = config["workshop"]["queue_approval_skipped"]
    workshop.ballet_status = READY if report.issue_type in skipped and not workshop.picked else PROPOSED
    draft = _folder(workshop, home) / "issue.md"
    draft.write_text(_issue_text(report), encoding="utf-8")
    specs = Path(workshop.worktree) / config["project"]["specs"]
    workshop.issue, notes = ballet_github.publish_issue_with_links(draft, report.issue_type, workshop.ballet_status, run=tools.gh, specs=specs)
    _log(home, workshop, "published", {"item": workshop.framed or workshop.item, "issue": workshop.issue, "type": report.issue_type,
                                       "status": workshop.ballet_status, "picked": workshop.picked,
                                       "decided_alone": len(report.decided), "exchanges": len(workshop.exchanges)})
    return [f"issue #{workshop.issue} published as {report.issue_type}, Ballet status {workshop.ballet_status}", *notes]


def _issue_text(report):
    """Le brouillon du Dramaturg, avec ce qu'il a décidé seul : le Director le lit dans l'issue pour l'accepter."""
    if not report.decided:
        return report.draft
    lines = "\n".join(f"- {line}" for line in report.decided)
    return f"{report.draft.rstrip()}\n\n{DECIDED_HEADING}\n\n{lines}\n"


def _mark_decided_alone(workshop, report, tools):
    """`ballet:decided-alone` sur l'issue dont le Dramaturg a décidé quelque chose seul."""
    if not report.decided or workshop.marked:
        return []
    ballet_github.mark_decided_alone(workshop.issue, run=tools.gh)
    workshop.marked = True
    return [f"issue #{workshop.issue} marked ballet:decided-alone ({len(report.decided)} decision(s))"]


def _publish_exchanges(workshop, home, tools):
    """Les échanges avec le Choreographer, un commentaire chacun sur l'issue, dans l'ordre : la trace que la Rehearsal
    publie au fil de l'eau, ici à la naissance de l'issue. Chaque commentaire est compté : une reprise ne le redouble pas."""
    for text in workshop.exchanges[workshop.exchanges_published:]:
        message = _folder(workshop, home) / f"exchange-{workshop.exchanges_published + 1}.md"
        message.write_text(text, encoding="utf-8")
        ballet_github.comment_issue(workshop.issue, message, run=tools.gh)
        workshop.exchanges_published += 1
    return [f"{len(workshop.exchanges)} exchange(s) with the choreographer published on #{workshop.issue}"] if workshop.exchanges else []


# --- lecture du rapport -------------------------------------------------------


def _read_report(text, needs_item=False):
    """Le type de l'issue et son brouillon : la section `## Issue draft` va jusqu'à la fin du rapport. Une demande capturée
    nomme aussi sa ligne du backlog (`- Item:`)."""
    head, _, draft = text.partition(ISSUE_DRAFT_HEADING)
    item = _report_field(head, "Item")
    if needs_item and not WORKSHOP_ITEM.match(item):
        raise WorkshopError(f"the report's `- Item:` is '{item}', expected the backlog line of the request (OPP-N, FEAT-N, BUG-N or TASK-N)")
    issue_type = _report_field(head, "Type")
    if issue_type not in ballet_github.PUBLISHED_TYPES:
        raise WorkshopError(f"the report's `- Type:` is '{issue_type}', expected {', '.join(ballet_github.PUBLISHED_TYPES)}")
    if not draft.strip():
        raise WorkshopError(f"the report has no `{ISSUE_DRAFT_HEADING}` section")
    return Report(issue_type, draft.strip() + "\n", _decided_alone(head), item)


def _decided_alone(text):
    """Les lignes de `## Decided alone`, jusqu'à la section suivante ; aucune si le Dramaturg n'a rien décidé seul."""
    section = re.search(rf"^{DECIDED_HEADING}[ \t]*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return re.findall(r"^- (.+?)\s*$", section.group(1), re.MULTILINE) if section else []


def _report_field(text, name):
    match = re.search(rf"^- {name}:\s*(.+?)\s*$", text, re.MULTILINE)
    return match.group(1) if match else ""


# --- état, journal et lectures ------------------------------------------------


def _settle(workshop, step, home):
    """Le pas fixe le statut de la session ; l'état est sauvé et le pas journalisé. C'est une transition de l'élément,
    que Maestro apprend si elle escalade ou finit."""
    workshop.status = ballet_rehearsal.STATUS_OF_STEP[step.next]
    workshop.reason = step.reason
    _save(workshop, home)
    _log(home, workshop, step.next, {"reason": step.reason, "done": step.done})
    step.item = workshop.item
    return step


def _over(workshop):
    return Step("done", workshop.reason, [f"nothing to do: the Workshop {workshop.item} is over"])


def _save(workshop, home):
    _state_path(workshop.item, home).write_text(json.dumps(asdict(workshop), indent=2) + "\n", encoding="utf-8")


def _load(item, home):
    path = _state_path(item, home)
    if not path.is_file():
        raise WorkshopError(f"no Workshop of {item} in {path.parent}")
    return Workshop(**json.loads(path.read_text(encoding="utf-8")))


def next_item(home):
    """L'élément qu'un Workshop autopilot sans nom choisirait dans ce projet : la première ligne de *Next up* sans Workshop."""
    return _pick_in_backlog(_checked_config(home), home)


def _pick_in_backlog(config, home):
    """L'élément du Workshop qui choisit seul : la première ligne de *Next up* (rangée par le Dramaturg avec le Director)
    qui n'a encore aucune session ici. Les lignes `CAP-` n'en sont pas : une capability se découpe d'abord."""
    backlog = Path(home) / config["project"]["specs"] / "backlog.md"
    if not backlog.is_file():
        raise WorkshopError(f"no backlog at {backlog}: nothing to pick from")
    for item in _next_up(backlog.read_text(encoding="utf-8")):
        if not _state_path(item, home).is_file():
            return item
    raise WorkshopError(f"*Next up* in {backlog} has no OPP, FEAT, BUG or TASK line left that has no Workshop yet: name an item")


def _free_slug(request, home):
    """Le nom d'une session sur une demande hors backlog : ses premiers mots, sans accents ; suffixé quand ce nom a déjà
    servi (le journal ne confond jamais deux sessions)."""
    base = _slug(request)
    if not base:
        raise WorkshopError("the request has no word to name its session")
    slug, rank = base, 1
    while _state_path(slug, home).is_file():
        rank += 1
        slug = f"{base}-{rank}"
    return slug


def _slug(text):
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return "-".join(re.findall(r"[a-z0-9]+", plain)[:SLUG_WORDS])


def _next_up(text):
    """Les éléments de la section *Next up*, dans l'ordre du backlog."""
    _, _, after = text.partition(NEXT_UP_HEADING)
    section = re.split(r"^## ", after, maxsplit=1, flags=re.MULTILINE)[0]
    return NEXT_UP_LINE.findall(section)


def _refuse_if_open(item, home):
    path = _state_path(item, home)
    if path.is_file() and json.loads(path.read_text(encoding="utf-8"))["status"] != "done":
        raise WorkshopError(f"the Workshop of {item} is already open ({path})")


def open_workshops(home):
    found = [Workshop(**json.loads(path.read_text(encoding="utf-8"))) for path in sorted(_run_dir(home).glob(f"{WORKSHOP_PREFIX}*.json"))]
    return [workshop for workshop in found if workshop.status != "done"]


def _log(home, workshop, event, detail):
    entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "workshop": workshop.item, "event": event, "detail": detail}
    with (_run_dir(home) / "journal.jsonl").open("a", encoding="utf-8") as journal:
        journal.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _state_path(item, home):
    return _run_dir(home) / f"{WORKSHOP_PREFIX}{item}.json"


def _folder(workshop, home):
    folder = _run_dir(home) / f"{WORKSHOP_PREFIX}{workshop.item}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _run_dir(home):
    folder = Path(home) / RUN_DIR
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _checked_config(home):
    try:
        config = ballet_config.effective_config(home)
    except ballet_config.ConfigError as error:
        raise WorkshopError(str(error)) from error
    problems = ballet_config.find_problems(config)
    if problems:
        raise WorkshopError("the profile is not valid, run /ballet:init-project: " + "; ".join(problems))
    return config


def _repo(config, home):
    repos = config.get("repos", {})
    if len(repos) != 1:
        raise WorkshopError("the Conductor v0 runs a single repo; this profile declares " + str(len(repos)))
    return str((Path(home) / next(iter(repos.values()))["path"]).resolve())


def _open_worktree(workshop, tools):
    path = ballet_orca.open_worktree(workshop.repo, workshop.branch, tools)
    if not path:
        raise WorkshopError(f"no worktree found for {workshop.branch} after its creation")
    return path


def _received_step(workshop, message, config, home, tools):
    """Le pas d'un message lu chez Orca, noté comme reçu avant d'être traité : même en escalade, il n'est jamais rejoué."""
    if message.get("id") and message["id"] not in workshop.received:
        workshop.received.append(message["id"])
    try:
        return _handle_worker_message(workshop, message, config, home, tools)
    except ERRORS as error:
        return Step("escalate", str(error))


def _is_new_for(workshop, message):
    """Un message du Run qui revient à ce Workshop : de son Dramaturg ou de son Choreographer, et pas encore traité."""
    workers = {workshop.dispatch, workshop.advisor_dispatch} - {""}
    return message.get("id") not in workshop.received and ballet_orca.worker_dispatch(message) in workers


def _nothing_new(workshop, run_id, ignored):
    """Rien pour le Workshop dans le Run : son état ne bouge pas, et le pas le redit."""
    return Step(ballet_rehearsal.STEP_OF_STATUS[workshop.status], workshop.reason,
                [f"no new message for Workshop {workshop.item} in Orca run {run_id}" + (f" ({ignored} ignored)" if ignored else "")])


def _merged_steps(workshop, steps, left, ignored):
    """Les pas des messages traités en un seul : leurs lignes, puis ce qui reste à recevoir ; le `NEXT` du dernier."""
    last = steps[-1]
    done = [line for step in steps for line in step.done]
    done += [f"not processed after this step, still to receive: receive {workshop.item} --message {message['id']}" for message in left]
    done += [f"{ignored} message(s) of the run ignored: not for Workshop {workshop.item}, or already received"] if ignored else []
    return Step(last.next, last.reason, done, item=last.item)


def _orca_message(wanted, by, tools):
    message = ballet_orca.inbox_message(wanted, by, tools)
    if not message:
        raise WorkshopError(f"no Orca message {'from dispatch ' if by == 'dispatch' else ''}{wanted} in the inbox")
    return message


def _parsed(body):
    try:
        return parse_message(body)
    except MessageError as error:
        raise WorkshopError(f"invalid message, send it back to its author: {error}") from error


# --- ligne de commande --------------------------------------------------------

USAGE = ("usage: begin [<item>] | begin --request \"<request>\" | receive [<item>] --run <run-id> | receive [<item>] --message <msg-id> | receive [<item>] --dispatch <ctx-id> "
         "| resume [<item>] | status [<item>]   (an item: a line of the backlog, OPP-N, FEAT-N, BUG-N or TASK-N, or the slug of a request's Workshop; "
         "no <item> after receive, resume or status: the only open Workshop; none after begin: the Workshop picks the "
         "first line of Next up that has no Workshop yet)")


def main(argv, home=".", tools=None):
    """Affiche le pas et sort avec 0, escalade comprise ; 2 sur un usage invalide."""
    tools = tools or Tools()
    command, arguments = (argv[1], argv[2:]) if len(argv) > 1 else (None, [])
    try:
        step = _command(command, arguments, home, tools)
        ballet_maestro.announce(step, home, tools.orca)
        print(step.render())
    except UsageError as error:
        print(error, file=sys.stderr)
        return 2
    except ERRORS as error:
        step = Step("escalate", str(error), item=_named_item(command, arguments))
        ballet_maestro.announce(step, home, tools.orca)
        print(step.render())
    return 0


OPTIONS = ("--request", "--run", "--message", "--dispatch")


def _command(command, arguments, home, tools):
    _refuse_help_and_unknown_options(command, arguments)
    if command == "begin" and len(arguments) == 2 and arguments[0] == "--request":
        return begin(None, home, tools, request=arguments[1])
    if command == "begin" and len(arguments) <= 1:
        return begin(_item(arguments[0]) if arguments else None, home, tools)
    if command in ("receive", "resume", "status"):
        item, rest = _item_and_rest(arguments, home)
        if command == "receive" and len(rest) == 2 and rest[0] == "--run":
            return receive_from_run(item, rest[1], home, tools)
        if command == "receive" and len(rest) == 2 and rest[0] in ("--message", "--dispatch"):
            return receive_from_orca(item, rest[1], home, tools, by=rest[0][2:])
        if command == "resume" and not rest:
            return resume(item, home, tools)
        if command == "status" and not rest:
            return status(item, home, tools)
    raise UsageError(USAGE)


def _refuse_help_and_unknown_options(command, arguments):
    """`--help`, `-h` ou une option inconnue : l'usage, rien d'autre (ni état touché, ni Orca, ni Maestro)."""
    request_text = arguments[1:2] if command == "begin" and arguments[:1] == ["--request"] else []
    options = [argument for argument in arguments if argument.startswith("-") and argument not in request_text]
    if command in ("-h", "--help") or any(option not in OPTIONS for option in options):
        raise UsageError(USAGE)


def _named_item(command, arguments):
    """L'élément nommé sur la ligne de commande (`BUG-004`), sinon `?` : une panne est annoncée à Maestro même avant
    que la session existe. Rien pour `status`, une simple lecture."""
    if command == "status":
        return ""
    return next((argument for argument in arguments if WORKSHOP_ITEM.match(argument)), "?")


def _item(text):
    if not WORKSHOP_ITEM.match(text):
        raise UsageError(f"not an item: {text}\n" + USAGE)
    return text


def _item_and_rest(arguments, home):
    """L'élément (ou le slug d'une session) nommé en tête des arguments, sinon la seule session ouverte."""
    if arguments and (WORKSHOP_ITEM.match(arguments[0]) or (SLUG.match(arguments[0]) and _state_path(arguments[0], home).is_file())):
        return arguments[0], arguments[1:]
    return _only_open_workshop(home), arguments


def _only_open_workshop(home):
    workshops = open_workshops(home)
    if len(workshops) != 1:
        listed = ", ".join(workshop.item for workshop in workshops) or "none"
        raise UsageError(f"{len(workshops)} Workshops are open ({listed}): name the item\n" + USAGE)
    return workshops[0].item


if __name__ == "__main__":
    sys.exit(main(sys.argv))
