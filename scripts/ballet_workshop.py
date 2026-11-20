"""Le Conductor du Workshop en autopilot : l'état d'une session de Workshop, ses transitions, et chaque action qu'elles déclenchent.

    python3 ballet_workshop.py begin   <élément>                        # ouvre la session de l'élément : le Dramaturg le cadre
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
"""

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import ballet_config
import ballet_github
import ballet_orca
import ballet_policy
import ballet_rehearsal
from ballet_message import MessageError, parse_message
from ballet_rehearsal import RehearsalError, Step, Tools, UsageError

RUN_DIR = ballet_rehearsal.RUN_DIR
WORKSHOP_PREFIX = "workshop-"
WORKSHOP_ITEM = re.compile(r"^(?:OPP|FEAT|BUG|TASK)-\d+$")
ISSUE_DRAFT_HEADING = "## Issue draft"
PROPOSED, READY = "proposed", "ready"
MAX_NUDGES = 1
MAX_REFUSED_REPORTS = 1
FRAMING = """Frame {item}, a line of the backlog: make it one ready feature (or, for a bug or a task, the line that reaches the top of *Next up*) in the specs space, committed on this branch with the skill's commit messages. Write no plan and no code. Do not publish the issue: the script does, once your specs are on `main`.

Your report (a Ballet message, `type: report`, `from: dramaturg`, `to: conductor`, subject `{item}`) holds, in this order:
- `- Type: Feature`, `- Type: Bug` or `- Type: Task`: the type of the issue to publish;
- `## Decided alone`: one line per business decision you made without the Director, with your reason (the Director reads them to accept the proposal);
- `## Issue draft`: always the last section, the issue body to its end, from the template `issue.md` without its plan, its first line the title `# FEAT-NNN · <name>` (`BUG-NNN`, `TASK-NNN`).

When the item cannot be framed (it is not in the backlog, there is nothing to build, only the Director can settle a question), write nothing and report `- Blocked: <why>`, nothing else."""


class WorkshopError(Exception):
    """Le Workshop ne peut pas avancer : le Conductor escalade."""


ERRORS = (WorkshopError, RehearsalError, ballet_github.GitHubError)   # `Tools.run` lève une RehearsalError


@dataclass
class Workshop:
    """Une session de Workshop : un élément du backlog, son worktree, son Dramaturg, et jusqu'où ses specs et son issue sont allées."""
    item: str                                   # `OPP-12`, `FEAT-007`, `BUG-004`, `TASK-009`
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

    @property
    def branch(self):
        return f"workshop/{self.item}"


@dataclass
class Report:
    """Ce que le script lit dans le rapport du Dramaturg."""
    issue_type: str
    draft: str


# --- les entrées du Conductor -------------------------------------------------


def begin(item, home, tools):
    """Ouvre la session de l'élément : un worktree sur `workshop/<élément>`, depuis `main`, et le Dramaturg qui le cadre."""
    config = _checked_config(home)
    _refuse_if_open(item, home)
    workshop = Workshop(item=item, repo=_repo(config, home))
    workshop.worktree = _open_worktree(workshop, tools)
    git = tools.git(workshop.worktree)
    workshop.checkpoint, workshop.refs = ballet_policy.head(git), ballet_policy.refs(git)
    _log(home, workshop, "begin", {"item": item})
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
        step = _handle_worker_message(workshop, _orca_message(wanted, by, tools), config, home, tools)
    except ERRORS as error:
        step = Step("escalate", str(error))
    return _settle(workshop, step, home)


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
    lines += [f"dramaturg: dispatch {workshop.dispatch or 'not started'}"]
    lines += [f"specs: pull request #{workshop.pull_request}{', merged' if workshop.merged else ''}"] if workshop.pull_request else []
    lines += [f"issue #{workshop.issue}, Ballet status {workshop.ballet_status}"] if workshop.issue else []
    return Step(ballet_rehearsal.STEP_OF_STATUS[workshop.status], workshop.reason, lines)


# --- le Dramaturg -------------------------------------------------------------


def _start_dramaturg(workshop, step, config, home, tools):
    try:
        _start_worker(workshop, config, home, tools)
    except ERRORS as error:
        return Step("escalate", f"the dramaturg could not start: {error}", step.done)
    return Step("wait", done=step.done + [f"dramaturg started on {workshop.item}"])


def _start_worker(workshop, config, home, tools):
    route = config["roles"]["dramaturg"]
    agent = ballet_rehearsal.ORCA_AGENTS.get(route.get("cli"))
    if not agent:
        raise WorkshopError(f"the dramaturg's CLI `{route.get('cli')}` cannot run as an Orca worker yet")
    spec = _write_spec(workshop, home)
    dispatch = ballet_orca.start_worker(spec, workshop.worktree, agent, f"Dramaturg · {workshop.item}", tools,
                                        model=route.get("model", ""))
    if not dispatch:
        raise WorkshopError("the worker started but its receipt names no dispatchId")
    workshop.dispatch = dispatch
    _log(home, workshop, "handoff", {"role": "dramaturg", "dispatch": dispatch, "how": "start", "agent": agent,
                                     "model": route.get("model", ""), "text": FRAMING.format(item=workshop.item)})


def _write_spec(workshop, home):
    path = _folder(workshop, home) / "dramaturg-1.md"
    path.write_text(_role_spec(workshop), encoding="utf-8")
    return path


def _role_spec(workshop):
    return f"""You are the Ballet Dramaturg of the autopilot Workshop on {workshop.item}, branch `{workshop.branch}`, in this worktree.

Load the skill `/ballet:dramaturg` and follow its section *In an autopilot Workshop*.

{FRAMING.format(item=workshop.item)}

Under the Conductor:
- Nobody answers a question in this Workshop: never ask. Decide within your perimeter, and write what you decided.
- When you are done: send your `worker_done`, whose body is your final message, whole, header line first. Ending your turn without sending it stops the Workshop.
- Never push, never run `gh`, never change branch.
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
    if sender != "dramaturg":
        raise WorkshopError(f"a message from the {sender}: only the dramaturg plays in this Workshop")
    if kind == "report":
        return _after_report(workshop, text, config, home, tools)
    if kind == "question":
        return Step("escalate", f"the dramaturg asks the {header['to']}, and nobody answers in an autopilot Workshop: see its message")
    if kind == "escalation":
        return Step("escalate", "the dramaturg escalates: see its message")
    raise WorkshopError(f"no transition for a {kind} from the dramaturg")


def _worker_stopped(workshop, message, home, tools):
    """Le Dramaturg a fini son tour sans `worker_done` : relancé pour envoyer son rapport, une fois ; ensuite, ou
    s'il est tombé en erreur, c'est au Director."""
    payload = ballet_orca.payload(message)
    if payload.get("dispatchId") != workshop.dispatch or payload.get("stopReason") != "finished" or workshop.nudges >= MAX_NUDGES:
        raise WorkshopError(f"Orca: {message.get('subject', 'a worker stopped')}: {message.get('body', '')[:300]}")
    workshop.nudges += 1
    _send(workshop, f"{workshop.item} · dramaturg: send your worker_done", ballet_rehearsal.REPORT_REMINDER, "nudge", home, tools)
    return Step("wait", done=["the dramaturg ended its turn without worker_done: asked to send its report"])


def _send(workshop, subject, body, how, home, tools):
    tools.orca(["orchestration", "send", "--to", f"dispatch:{workshop.dispatch}", "--subject", subject, "--body", body])
    _log(home, workshop, "handoff", {"role": "dramaturg", "dispatch": workshop.dispatch, "how": how, "text": body})


# --- après son rapport --------------------------------------------------------


def _after_report(workshop, text, config, home, tools):
    blocked = _report_field(text, "Blocked")
    if blocked:
        return Step("escalate", f"the dramaturg is blocked: {blocked}")
    try:
        _read_report(text)
    except WorkshopError as error:
        return _refused_report(workshop, error, home, tools)
    workshop.report = text
    return _finish(workshop, Step("wait"), config, home, tools)


def _refused_report(workshop, error, home, tools):
    """Un rapport sans type valide ou sans brouillon est renvoyé une fois au Dramaturg ; la deuxième fois, le Director décide."""
    workshop.refused_reports += 1
    if workshop.refused_reports > MAX_REFUSED_REPORTS:
        return Step("escalate", str(error))
    _send(workshop, f"{workshop.item} · dramaturg: complete your report", f"Your report is refused: {error}. Report again, whole.", "send", home, tools)
    return Step("wait", done=[f"report refused ({error}): sent back to the dramaturg"])


def _resumed(workshop, config, home, tools):
    if not workshop.dispatch:
        return _start_dramaturg(workshop, Step("wait"), config, home, tools)
    if workshop.report:
        return _finish(workshop, Step("wait"), config, home, tools)
    return Step(ballet_rehearsal.STEP_OF_STATUS[workshop.status], workshop.reason, ["nothing to resume: the dramaturg has not reported yet"])


def _finish(workshop, step, config, home, tools):
    """La politique juge le passage, les specs vont sur `main`, l'issue est publiée, le worktree est rangé. Chaque étape
    faite est retenue : une reprise après un échec repart de celle qui a échoué."""
    report = _read_report(workshop.report)
    if not workshop.merged:
        found = _policy(workshop, config, home, tools)
        if found:
            return _refused_by_policy(workshop, found, step, home, tools)
        step.done += _specs_to_main(workshop, tools)
    step.done.append(_publish_issue(workshop, report, config, home, tools))
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
    _send(workshop, f"{workshop.item} · dramaturg: fix your passage", _policy_fix_assignment(found), "send", home, tools)
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
    """L'issue du Workshop, publiée par le script : `proposed`, ou `ready` pour un type que le Director a dispensé de son oui."""
    if workshop.issue:
        return f"issue #{workshop.issue} already published as {workshop.ballet_status}"
    skipped = config["workshop"]["queue_approval_skipped"]
    workshop.ballet_status = READY if report.issue_type in skipped else PROPOSED
    draft = _folder(workshop, home) / "issue.md"
    draft.write_text(report.draft, encoding="utf-8")
    workshop.issue = ballet_github.publish_issue(draft, report.issue_type, workshop.ballet_status, run=tools.gh)
    return f"issue #{workshop.issue} published as {report.issue_type}, Ballet status {workshop.ballet_status}"


# --- lecture du rapport -------------------------------------------------------


def _read_report(text):
    """Le type de l'issue et son brouillon : la section `## Issue draft` va jusqu'à la fin du rapport."""
    head, _, draft = text.partition(ISSUE_DRAFT_HEADING)
    issue_type = _report_field(head, "Type")
    if issue_type not in ballet_github.PUBLISHED_TYPES:
        raise WorkshopError(f"the report's `- Type:` is '{issue_type}', expected {', '.join(ballet_github.PUBLISHED_TYPES)}")
    if not draft.strip():
        raise WorkshopError(f"the report has no `{ISSUE_DRAFT_HEADING}` section")
    return Report(issue_type, draft.strip() + "\n")


def _report_field(text, name):
    match = re.search(rf"^- {name}:\s*(.+?)\s*$", text, re.MULTILINE)
    return match.group(1) if match else ""


# --- état, journal et lectures ------------------------------------------------


def _settle(workshop, step, home):
    """Le pas fixe le statut de la session ; l'état est sauvé et le pas journalisé."""
    workshop.status = ballet_rehearsal.STATUS_OF_STEP[step.next]
    workshop.reason = step.reason
    _save(workshop, home)
    _log(home, workshop, step.next, {"reason": step.reason, "done": step.done})
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


def _refuse_if_open(item, home):
    path = _state_path(item, home)
    if path.is_file() and json.loads(path.read_text(encoding="utf-8"))["status"] != "done":
        raise WorkshopError(f"the Workshop of {item} is already open ({path})")


def _open_workshops(home):
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

USAGE = ("usage: begin <item> | receive [<item>] --message <msg-id> | receive [<item>] --dispatch <ctx-id> "
         "| resume [<item>] | status [<item>]   (an item: a line of the backlog, OPP-N, FEAT-N, BUG-N or TASK-N; "
         "no <item>: the only open Workshop)")


def main(argv, home=".", tools=None):
    """Affiche le pas et sort avec 0, escalade comprise ; 2 sur un usage invalide."""
    tools = tools or Tools()
    command, arguments = (argv[1], argv[2:]) if len(argv) > 1 else (None, [])
    try:
        print(_command(command, arguments, home, tools))
    except UsageError as error:
        print(error, file=sys.stderr)
        return 2
    except ERRORS as error:
        print(Step("escalate", str(error)).render())
    return 0


def _command(command, arguments, home, tools):
    if command == "begin" and len(arguments) == 1:
        return begin(_item(arguments[0]), home, tools).render()
    if command in ("receive", "resume", "status"):
        item, rest = _item_and_rest(arguments, home)
        if command == "receive" and len(rest) == 2 and rest[0] in ("--message", "--dispatch"):
            return receive_from_orca(item, rest[1], home, tools, by=rest[0][2:]).render()
        if command == "resume" and not rest:
            return resume(item, home, tools).render()
        if command == "status" and not rest:
            return status(item, home, tools).render()
    raise UsageError(USAGE)


def _item(text):
    if not WORKSHOP_ITEM.match(text):
        raise UsageError(f"not an item: {text}\n" + USAGE)
    return text


def _item_and_rest(arguments, home):
    """L'élément nommé en tête des arguments, sinon la seule session ouverte."""
    if arguments and WORKSHOP_ITEM.match(arguments[0]):
        return arguments[0], arguments[1:]
    return _only_open_workshop(home), arguments


def _only_open_workshop(home):
    workshops = _open_workshops(home)
    if len(workshops) != 1:
        listed = ", ".join(workshop.item for workshop in workshops) or "none"
        raise UsageError(f"{len(workshops)} Workshops are open ({listed}): name the item\n" + USAGE)
    return workshops[0].item


if __name__ == "__main__":
    sys.exit(main(sys.argv))
