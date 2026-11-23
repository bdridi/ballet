"""Le Conductor déterministe : l'état d'une Rehearsal, ses transitions, et chaque action qu'elles déclenchent.

    python3 ballet_rehearsal.py begin    <élément>                                 # ouvre la session de l'élément
    python3 ballet_rehearsal.py receive  <ID> --message <msg-id>                   # un message d'un worker, lu chez Orca par son id
    python3 ballet_rehearsal.py receive  <ID> --dispatch <ctx-id>                  # le dernier message du worker de ce dispatch
    python3 ballet_rehearsal.py receive  <ID> <message.md> [--question <msg-id>]   # un message écrit dans un fichier (le Director)
    python3 ballet_rehearsal.py receive  <ID> --mutation                           # la fin de la mutation, si son réveil s'est perdu
    python3 ballet_rehearsal.py premiere <ID>                                      # retente le merge (CI rouge ou trop longue)
    python3 ballet_rehearsal.py resume   <ID> | <élément>                          # applique la décision du Director (libellé de la PR)
    python3 ballet_rehearsal.py status   <ID> | <élément> [--json]                 # où en est la Rehearsal, ou la session
    python3 ballet_rehearsal.py nudge    [<ID>]                                    # rappelle au rôle attendu d'envoyer son message (OPP-75)

Lancé depuis le home du projet. Le skill `conductor` n'a qu'à appeler ce script et lire sa dernière ligne :
    NEXT: wait               un worker travaille ; Orca réveillera le Conductor
    NEXT: escalate <motif>   le Director décide ; la Rehearsal attend
    NEXT: done               la dernière Premiere de l'élément est faite : la session est finie

Une session joue un seul élément confié : une issue `Feature`, `Bug` ou `Task` (`#12`), ou une feature prête qui
n'a pas encore d'issue (`FEAT-002`, aussi `BUG-NNN`, `TASK-NNN`). Elle vit dans la base (`ballet_store.py`, table
`sessions`, clé `#12` ou `FEAT-002`) : l'élément, ses slices dans l'ordre du plan, la Rehearsal en cours, ce qui
est joué et le mode. Une Rehearsal à la fois dans une session ; à la Premiere d'une slice, le script ouvre lui-même la
suivante, depuis `main`. Deux sessions peuvent tourner côte à côte, sur deux éléments ; un même élément n'a qu'une
session ouverte. Combien de sessions à la fois, c'est l'affaire de celui qui les lance. Une escalade met la session en
pause : `resume` reprend la Rehearsal, puis la session. `<ID>` est facultatif pour `receive`, `premiere`, `resume`,
`status` et `nudge` quand une seule session est ouverte.

`nudge` (OPP-75) répond à un Conductor que Maestro relance parce que la Rehearsal n'écrit plus : le rôle attendu (le
destinataire de la question en attente, sinon celui du dernier `handoff`) reçoit `IDLE_REMINDER` dans sa session, et le
rappel est journalisé en relance. Le Director qu'on attend, ou une mutation en cours : rien n'est envoyé.

Le mode est le champ `Rehearsal mode` de l'issue (vide : `assisted`). En `assisted`, le plan attend le Director selon
le champ `Plan approval` de l'issue (`required`, `skipped`), sinon selon le profil (`[rehearsal] plan_approval`, `true`
par défaut) ; une feature sans issue suit le profil, l'`autopilot` n'attend jamais. Le script écrit le champ `Ballet status` à des
points fixes, seulement quand il change : `in-rehearsal` tant que la session joue, `plan-review` tant que le plan est en
review, `escalated` à une escalade, `done` à la dernière Premiere.

Une feature ouvre une Rehearsal de planification : le Choreographer seul, en mode auto, crée l'issue et ses slices. À
son rapport, le script lit l'issue et ses slices sur GitHub (`Part of #N` en première ligne) et les met en tête de la
session ; la première se joue dans le worktree de la planification (sa branche est renommée), avec les ADR du
Choreographer, qui restent à son nom pour la politique. Une issue sans plan suit le même chemin. Quand le plan attend
le Director, la session s'arrête alors pour sa review, une discussion qui passe par le Conductor : le Director écrit au
Choreographer un message `question` (il répond sans toucher au plan), `revise` (il amende le plan et ses slices, puis
refait son rapport) ou `approve` (le Dancer part). Chaque échange est publié sur l'issue planifiée.

Une escalade avec une PR pose `ballet:escalated` ; le Director tranche en posant `ballet:approved` (Premiere)
ou `ballet:rejected` avec un commentaire de PR (renvoi au Dancer), puis fait reprendre la Rehearsal (`resume`).

Un rapport du Dancer dont une tâche cochée n'a pas sa ligne `Red:` (le test et son échec, vus avant le code) est
refusé avant tout : rien ne tourne, le Dancer le complète ; la seconde fois, escalade. Les tests qu'il déclare renommés
(`- Renamed test: <ancien> → <nouveau>`) passent à la politique, qui juge la branche face à son point de départ (le
`HEAD` du worktree à son ouverture).

À chaque rapport du Dancer, après la politique, le script lance lui-même la preuve du repo (`proof` du profil) dans
le worktree, sans croire le rapport sur parole (`proof-start` et `proof-end` au journal) ; déjà verte sur ce commit,
elle ne repasse pas (`proof-reused`). Le Critic ne la relance pas, ni la mutation. Rouge, ou un worktree sali par la preuve : rien
n'est poussé, le Critic n'est pas mobilisé, le Dancer reprend avec la fin de la sortie ; au-delà de `max_round_trips`
preuves rouges, ou une preuve encore en cours après `proof_timeout_seconds`, la Rehearsal escalade.

La preuve verte, la branche part au Critic et, en même temps, le test de mutation (`ballet_mutation.py`, les entrées
`[[repos.<repo>.mutation]]` du profil) part en arrière-plan (`mutate <ID>`, interne) : le Critic ne la lit pas, il juge
seulement les exclusions. À sa fin, la mutation réveille le Conductor par un message Orca au Run de ses workers ; le
Conductor le reçoit comme les autres (`receive --message`). Le verdict du Critic et le code de sortie de chaque outil
décident ensemble, quand les deux sont là (le premier arrivé attend l'autre : `held_verdict` ou `mutation_red`) :
approuvé et verte, la Premiere ; rouge, c'est un point bloquant : le Dancer reprend, en un seul tour, avec les points du
Critic et les survivants, puis le Critic relit (même s'il avait approuvé) ; au-delà de `max_round_trips` mutations
rouges, ou après `[mutation] timeout_seconds`, la Rehearsal escalade. Une escalade du Critic n'attend pas la mutation.
`[mutation] enabled = false`, aucune entrée, ou un diff qui ne
touche aucun outil : le nœud est sauté (`mutation-skipped` au journal). Après une mutation verte, la suivante ne porte
que sur ce qui a changé depuis son commit. Un outil vert qui ne prouve rien (aucun mutant viable testé, rapport
absent ou illisible ; « no mutant in the diff » reste vert) n'est pas vert (`mutation-inconclusive`) : si la mutation
ne couvrait que les derniers changements, elle est relancée une fois sur toute la branche depuis son point de départ ;
sinon, ou si cette relance ne prouve rien non plus, la Rehearsal escalade.

Les notes d'une approbation ne retournent pas au Dancer : avant la Premiere, elles vont dans l'issue de dette technique
du projet (`ballet_github.file_technical_debt` : une Task `proposed`, libellé `technical-debt`, une section par PR), que
le Director passe `ready` quand il veut la jouer. Les notes d'un rejet, le Dancer les prend avec les points bloquants.
Une question adressée au Conductor, qui ne fait que relayer, va au Director.

À chaque rapport du Dancer, le script compte la taille du diff (`ballet_size.py`) et la journalise (`diff-size`).
Au-delà de `max_diff_lines`, la PR porte `ballet:oversized` ; en mode strict (`max_diff_strict`), la Rehearsal
escalade avant le Critic, jusqu'à ce que le Director pose `ballet:size-accepted` et la fasse reprendre.

La Premiere attend une CI en cours (`ci_wait_seconds`, un sondage toutes les 15 s) ; une CI rouge, ou encore
en cours à l'échéance, refuse le merge et escalade. Ces appels peuvent donc durer plusieurs minutes.

Après chaque passage d'un rôle, la politique (`ballet_policy.py`) vérifie ce qu'il a fait du repo, et le journalise
(`policy`). Une violation n'est jamais poussée : le rôle la corrige une fois, la deuxième escalade ; un Critic
ou un rôle qui répond (Choreographer, Dramaturg) en violation escalade tout de suite.

Un worker qui finit son tour sans `worker_done` est relancé une fois pour envoyer son rapport ; s'il recommence,
ou s'il est tombé en erreur, la Rehearsal escalade.

Une escalade est un cas prévu : le script sort avec 0. Il sort avec 2 sur un usage invalide,
et un autre code ≠ 0 n'est qu'une panne du script.

Une transition qui finit en `NEXT: escalate` ou `NEXT: done` est annoncée à Maestro (`ballet_maestro.announce`) : un
`status` dans sa boîte, sujet `<projet>#<élément> · <événement>`. Sans boîte, rien ; un échec n'est qu'une ligne du pas.

Le journal garde, texte entier, chaque message reçu (`message`) et tout ce que le Conductor remet à un worker
(`handoff` : `start`, `send`, `reply` ou `nudge`) : la Scène le lit.

L'état et le journal vivent dans la base de la machine (`ballet_store.py`, OPP-79) : chaque événement est rangé sur son
nœud (la Rehearsal, le tour d'un rôle, la preuve, la mutation, l'attente du Director). Les fichiers de travail (missions
des workers, résultats de la mutation, messages à publier, message du Director à recevoir) sont dans
`~/.ballet/projects/<alias>/` : rien n'est écrit dans le projet.
"""

import contextlib
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import ballet_config
import ballet_frictions
import ballet_github
import ballet_legacy
import ballet_maestro
import ballet_mutation
import ballet_orca
import ballet_policy
import ballet_size
import ballet_store
from ballet_message import MessageError, notes_of, parse_message, read_message, verdict_of

INBOX = "inbox.md"
PROOF_LOCK = "proof.lock"
ISSUE_ITEM = re.compile(r"^#?(\d+)$")
FEATURE_ITEM = re.compile(r"^(?:FEAT|BUG|TASK)-\d{3}$")
QUEUED_TYPES = ("Feature", "Bug", "Task")   # ce qu'une session joue ; une `Slice` suit sa feature
SLICE_TYPE = "Slice"
DEFAULT_MODE = "assisted"
AUTOPILOT = "autopilot"
REHEARSAL_MODES = (DEFAULT_MODE, AUTOPILOT)          # le champ Rehearsal mode de l'issue ; vide, `assisted`
PLAN_APPROVALS = {"required": True, "skipped": False}    # le champ Plan approval de l'issue ; vide, le profil
PLAN_REVIEW_MESSAGES = ("question", "revise", "approve")  # ce que le Director écrit au Choreographer sur un plan en review
REHEARSAL_ID = re.compile(r"^((?:FEAT|BUG|TASK)-\d{3}(?:\.\d+)?)\b")
ORCA_AGENTS = {"claude": "claude", "codex": "codex", "grok": "grok", "opencode": "opencode"}
SKILLS_ROOT = Path(__file__).resolve().parent.parent / "skills"
STATUS_OF_STEP = {"wait": "open", "escalate": "escalated", "done": "done"}
STEP_OF_STATUS = {status: step for step, status in STATUS_OF_STEP.items()}
CI_POLL_SECONDS = 15
MAX_NUDGES = 1
MAX_POLICY_RESENDS = 1
MAX_MISPLACED = 1         # un `report` mal placé du Choreographer est renvoyé une fois, puis escalade
PROOF_OUTPUT_LINES = 60   # la fin de la sortie d'une preuve rouge, remise au Dancer
ANSWERING_ROLES = ("choreographer", "dramaturg")   # vérifiés à chaque réponse, sur la branche de Rehearsal
MAX_SLICES = 3            # au plus, par feature : une slice par critère, ou par groupe de critères
TASK_LINE = re.compile(r"^- \[([ xX])\]\s*(.+?)(?:\s+—\s+.*)?$")   # une tâche du rapport du Dancer
RED_LINE = re.compile(r"^- Red:\s*\S")                                 # son rouge, sous elle
RENAMED_TEST = re.compile(r"^\s*- Renamed test:\s*(.+?)\s*(?:→|->)\s*(.+?)\s*$", re.MULTILINE)
IDLE_REMINDER = ("Ballet has received nothing from you for a while. If you already sent your message (report, answer, verdict or "
                 "question), send it again now, whole, header line first, as your worker_done; otherwise finish your work and send it.")
REPORT_REMINDER = "You ended your turn without sending your worker_done. Send it now: its body is your final message, whole, header line first. Do not redo any work."


class RehearsalError(Exception):
    """La Rehearsal ne peut pas avancer : le Conductor escalade."""


class UsageError(Exception):
    """La commande est mal formée : rien n'a été fait."""


@dataclass
class Rehearsal:
    id: str
    issue: str
    repo: str
    worktree: str = ""
    pull_request: str = ""
    round_trips: int = 0
    reviews: int = 0                                 # verdicts APPROVED ou REJECTED reçus du Critic : son tour de review
    rounds: dict = field(default_factory=dict)       # "sujet|de>à" → dernier round vu
    dispatches: dict = field(default_factory=dict)   # rôle → dispatch Orca de son worker (le dernier : Orca en rouvre un à chaque envoi)
    handles: dict = field(default_factory=dict)      # rôle → handle Orca de son worker, qui ne change pas d'un dispatch à l'autre
    misplaced: dict = field(default_factory=dict)    # rôle → messages renvoyés parce que mal typés (un `report` au lieu d'une `answer`)
    pending: list = field(default_factory=list)      # questions en attente : {id, from, to}
    status: str = "open"                             # open | escalated | done
    reason: str = ""                                 # le motif de la dernière escalade, ou de la fin
    label: str = ""                                  # le dernier verdict posé en libellé par le script
    size: dict = field(default_factory=dict)         # la dernière mesure du diff
    blocked_on: str = ""                             # "size" : le Critic attend que le Director accepte la taille
    notes: str = ""                                  # l'issue de dette technique où les notes de l'approbation sont allées (`#N`)
    nudges: dict = field(default_factory=dict)       # rôle → relances sans `worker_done`, remis à zéro à son prochain message
    checkpoint: str = ""                             # `HEAD` du worktree quand le dernier rôle a reçu la main
    refs: list = field(default_factory=list)         # branches et tags au dernier passage en règle
    owned: list = field(default_factory=list)        # les commits du Choreographer et du Dramaturg, vérifiés à leur passage
    violations: dict = field(default_factory=dict)   # rôle → passages refusés par la politique
    red_proofs: int = 0                              # rapports du Dancer dont la preuve, lancée par le script, était rouge
    mutations: int = 0                               # mutations lancées : le tour de la dernière
    red_mutations: int = 0                           # mutations rouges
    mutation: dict = field(default_factory=dict)     # la mutation en cours : {round, head, run, started, whole}
    held_verdict: dict = field(default_factory=dict)  # le verdict du Critic qui attend la fin de la mutation : {verdict, text}
    mutation_red: list = field(default_factory=list)  # les outils rouges d'une mutation finie, qui attendent le verdict
    plan: str = ""                                   # review (le Director approuve le plan) | auto
    feature: str = ""                                # la feature d'une Rehearsal de planification, sans issue au départ
    plan_issue: str = ""                             # l'issue dont le plan est en review
    queued: list = field(default_factory=list)       # les slices du plan mises en tête de la session
    planned_by: str = ""                             # la Rehearsal de planification dont elle a pris le worktree
    session: str = ""                                # l'élément de sa session : `#12` ou `FEAT-002`
    base: str = ""                                   # le `HEAD` du worktree à son ouverture : le point de départ de la branche
    dancer_start: str = ""                           # le `HEAD` que le Dancer a reçu à sa première mission : ce qu'il a fait en part
    proven: str = ""                                 # le `HEAD` de la dernière preuve verte
    mutated: str = ""                                # le `HEAD` de la dernière mutation verte : la suivante part de là
    renamed_tests: dict = field(default_factory=dict)  # les tests renommés que le Dancer déclare : ancien nom → nouveau
    refused_reports: int = 0                         # rapports du Dancer refusés pour une ligne `Red:` manquante
    received: list = field(default_factory=list)     # les ids des messages Orca déjà traités : `receive --run` ne les rejoue pas
    frictions: dict = field(default_factory=dict)    # à sa fin : {seconds, frictions} (`ballet_frictions`), aussi au journal

    @property
    def branch(self):
        return f"rehearsal/{self.id}"


@dataclass
class Session:
    """Une session de Conductor : un élément confié (une Feature, un Bug ou une Task) et ses slices, une Rehearsal
    à la fois, jusqu'à sa dernière Premiere."""
    item: str                                       # `#12`, ou `FEAT-002` tant que la feature n'a pas d'issue
    mode: str = DEFAULT_MODE                        # le champ Rehearsal mode de l'issue
    issue: str = ""                                 # l'issue de l'élément ; celle d'une feature se connaît à son plan
    current: str = ""                               # la Rehearsal en cours
    items: list = field(default_factory=list)       # à jouer : l'élément, puis ses slices dans l'ordre du plan
    played: list = field(default_factory=list)      # {item, rehearsal}, dans l'ordre
    status: str = "open"                            # open | done
    ballet_status: str = ""                         # le dernier Ballet status connu de l'issue
    plan_approval: bool = False                     # le plan attend le Director avant le Dancer
    plan_approval_from: str = ""                    # d'où vient ce choix : issue, project ou autopilot
    frictions: dict = field(default_factory=dict)   # à sa fin : Rehearsal jouée → ses frictions

    @property
    def plan(self):
        """`review` : le plan attend la review du Director ; `auto` : le Dancer enchaîne."""
        return "review" if self.plan_approval else "auto"


@dataclass
class Step:
    """Ce que le Conductor fait ensuite : `wait`, `escalate` ou `done`, avec ce qui s'est passé."""
    next: str
    reason: str = ""
    done: list = field(default_factory=list)
    item: str = ""        # l'élément dont ce pas est une transition (annoncée à Maestro) ; vide pour une simple lecture

    def render(self):
        lines = [f"- {action}" for action in self.done]
        return "\n".join(lines + [f"NEXT: {self.next} {self.reason}".rstrip()])


@dataclass
class Proof:
    """Ce qu'a donné la preuve du repo : verte ou non, sa sortie, et si elle a dépassé son temps."""
    passed: bool
    output: str = ""
    timed_out: bool = False
    reused: bool = False      # déjà verte sur ce commit : pas relancée


class Tools:
    """Les commandes externes (git, gh, orca, la preuve, la mutation et son lancement en arrière-plan) et l'attente,
    remplaçables dans les tests."""

    def __init__(self, run=None, sleep=None, prove=None, launch=None, mutate=None):
        self.run = run or _run
        self.sleep = sleep or time.sleep
        self.prove = prove or _run_proof
        self.launch = launch or _launch_detached
        self.mutate = mutate or ballet_mutation.run_command_with_timeout

    def gh(self, arguments):
        return self.run(["gh", *arguments])

    def git(self, repo):
        return lambda arguments: self.run(["git", "-C", repo, *arguments])

    def orca(self, arguments):
        return self.run([os.environ.get("ORCA_CLI_COMMAND", "orca"), *arguments])


# --- les entrées du Conductor -------------------------------------------------


def begin(item, home, tools):
    """Ouvre la session d'un élément et joue sa première Rehearsal ; ses slices suivent, chacune depuis `main` après
    la Premiere de la précédente. La session finit à la dernière Premiere de l'élément."""
    config = _checked_config(home)
    _refuse_if_in_session(item, home)
    session = _new_session(item, config, tools)
    _save_session(session, home)
    step = Step("wait", done=[_plan_approval_line(session)])
    return _follow_on_github(session.item, _play_next(session.item, step, home, tools), home, tools)


def _begin(item, session, home, tools):
    """Ouvre la Rehearsal d'un élément de la session : une issue (le Dancer si son plan a ses tâches, le Choreographer
    sinon), ou une feature prête (la planification : le Choreographer seul)."""
    config = _checked_config(home)
    rehearsal, first_role = _rehearsal_of(item, config, home, tools)
    rehearsal.plan, rehearsal.session = session.plan, session.item
    _refuse_if_already_open(rehearsal, home)
    step = Step("wait")
    rehearsal.worktree = _open_worktree(rehearsal, tools)
    step.done.append(f"worktree {rehearsal.worktree} on {rehearsal.branch}, from origin/main")
    _log(home, rehearsal, "begin", {"item": _item_of(rehearsal), "plan": rehearsal.plan, "mode": session.mode, "session": session.item})
    git = tools.git(rehearsal.worktree)
    rehearsal.checkpoint, rehearsal.refs = ballet_policy.head(git), ballet_policy.refs(git)
    rehearsal.base = rehearsal.checkpoint
    _start_worker(rehearsal, first_role, _first_assignment(first_role, rehearsal, config), config, home, tools)
    step.done.append(f"{first_role} started on {_target(rehearsal)}")
    _join_session(rehearsal, _item_of(rehearsal), home)
    return _settle(rehearsal, step, home, tools)


def receive(rehearsal_id, message_path, question_id, home, tools):
    """Un message écrit dans un fichier : celui du Director (une réponse)."""
    config = _checked_config(home)
    rehearsal = load(rehearsal_id, home)
    try:
        header, text = _message(message_path)
        step = _handle(rehearsal, header, text, question_id, config, home, tools)
    except (RehearsalError, ballet_github.GitHubError) as error:
        step = Step("escalate", str(error))
    return _settle(rehearsal, step, home, tools)


def receive_from_orca(rehearsal_id, wanted, home, tools, by="message"):
    """Le message d'un worker, lu chez Orca par son id (`by="message"`) ou comme le dernier de son dispatch
    (`by="dispatch"`, quand le réveil ne nomme que lui) : le Conductor ne le recopie pas."""
    config = _checked_config(home)
    rehearsal = load(rehearsal_id, home)
    try:
        step = _step_of_message(rehearsal, _orca_message(wanted, by, tools), config, home, tools)
    except (RehearsalError, ballet_github.GitHubError) as error:
        step = Step("escalate", str(error))
    return _settle(rehearsal, step, home, tools)


def receive_from_run(rehearsal_id, run_id, home, tools):
    """Le réveil qui ne nomme que le Run du Conductor (`orca orchestration check --run <run>`) : ses messages en attente
    sont consommés d'un coup ; ceux de la Rehearsal, pas encore traités, avancent dans l'ordre, chacun comme par
    `--message`, jusqu'au premier pas qui n'est pas `wait`. Les autres (une Rehearsal finie, un message déjà traité)
    sont ignorés."""
    config = _checked_config(home)
    rehearsal = load(rehearsal_id, home)
    batch = ballet_orca.run_messages(run_id, tools)
    mine = [message for message in batch if _is_new_for(rehearsal, message)]
    ignored = len(batch) - len(mine)
    if not mine:
        return _nothing_new(rehearsal, run_id, ignored)
    steps = []
    for message in mine:
        steps.append(_settle(rehearsal, _received_step(rehearsal, message, config, home, tools), home, tools))
        if steps[-1].next != "wait" or rehearsal.status != "open":
            break
    return _merged_steps(rehearsal, steps, mine[len(steps):], ignored)


def _kept_escalation(rehearsal, step):
    """Une Rehearsal déjà escaladée garde son motif : ce que la mutation y ajoute n'est qu'une ligne de plus."""
    if rehearsal.status != "escalated" or step.next != "escalate" or step.reason == rehearsal.reason:
        return step
    return Step("escalate", rehearsal.reason, step.done + [f"also: {step.reason}"])


def receive_mutation(rehearsal_id, home, tools):
    """La fin de la mutation en cours, sans son réveil Orca (perdu) : ses résultats sont lus dans `<dossier de travail>/<ID>/`."""
    config = _checked_config(home)
    rehearsal = load(rehearsal_id, home)
    try:
        step = _after_mutation(rehearsal, rehearsal.mutation.get("round"), config, home, tools)
    except (RehearsalError, ballet_github.GitHubError) as error:
        step = Step("escalate", str(error))
    return _settle(rehearsal, _kept_escalation(rehearsal, step), home, tools)


def mutate(rehearsal_id, home, tools):
    """La moitié en arrière-plan du nœud de mutation : les outils, leurs résultats dans `<dossier de travail>/<ID>/`, puis le
    réveil du Conductor. Quoi qu'il arrive, le Conductor est réveillé : une panne devient un résultat."""
    rehearsal = load(rehearsal_id, home)
    try:
        results = {"outcomes": [asdict(outcome) for outcome in _mutate_each_tool(rehearsal, _checked_config(home), home, tools)]}
    except Exception as error:  # le Conductor attend ce réveil : rien ne doit l'empêcher de partir
        results = {"error": f"{type(error).__name__}: {error}"}
    _mutation_results_path(rehearsal, home).write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _wake_the_conductor(rehearsal, home, tools)


def premiere(rehearsal_id, home, tools):
    config = _checked_config(home)
    rehearsal = load(rehearsal_id, home)
    return _settle(rehearsal, _then_premiere(rehearsal, Step("wait"), config, tools), home, tools)


def resume(rehearsal_id, home, tools):
    """Applique la décision du Director sur une Rehearsal escaladée, lue sur le libellé de sa PR."""
    config = _checked_config(home)
    rehearsal = load(rehearsal_id, home)
    if rehearsal.status != "escalated":
        return Step(STEP_OF_STATUS[rehearsal.status], rehearsal.reason, [f"nothing to resume: Rehearsal {rehearsal.id} is {rehearsal.status}"])
    try:
        step = _apply_decision(rehearsal, config, home, tools)
    except (RehearsalError, ballet_github.GitHubError) as error:
        step = Step("escalate", str(error))
    return _settle(rehearsal, step, home, tools)


def resume_session(session_item, home, tools):
    """Reprend la Rehearsal en cours de la session, ou, si la session s'est arrêtée avant d'ouvrir la suivante, l'ouvre."""
    session = _load_session(session_item, home)
    if session.current:
        return resume(session.current, home, tools)
    if session.items:
        return _follow_on_github(session.item, _play_next(session.item, Step("wait"), home, tools), home, tools)
    return Step("done", "", [f"nothing to resume: the session of {session.item} is over"])


def status(rehearsal_id, home, tools):
    """Où en est la Rehearsal, en clair : sa dernière ligne `NEXT` est celle du dernier pas."""
    config = _checked_config(home)
    rehearsal = load(rehearsal_id, home)
    summary = [_where(rehearsal), _pull_request_line(rehearsal, tools), _size_line(rehearsal), _round_trips_line(rehearsal, config)]
    summary += _mutation_lines(rehearsal)
    summary += _pending_lines(rehearsal) + _workers_line(rehearsal) + _session_lines(_session_of(rehearsal, home), rehearsal.id)
    return Step(STEP_OF_STATUS[rehearsal.status], rehearsal.reason, summary)


def nudge(rehearsal_id, home, tools):
    """Le Monitor a vu la Rehearsal sans nouvelles (OPP-75) : le rôle qu'elle attend reçoit un rappel de son dispatch.
    Rien n'est envoyé quand c'est le Director qu'on attend, ou la seule mutation (le verdict du Critic est déjà là).
    Le rappel est une relance au journal
    (`handoff` `nudge`) ; un pas `wait` n'est pas journalisé : ce n'est pas de l'activité, et le Monitor la verrait."""
    rehearsal = load(rehearsal_id, home)
    if rehearsal.status != "open":
        return Step(STEP_OF_STATUS[rehearsal.status], rehearsal.reason, [f"nothing to remind: Rehearsal {rehearsal.id} is {rehearsal.status}"])
    if rehearsal.mutation and rehearsal.held_verdict:
        return Step("wait", done=[f"the mutation (round {rehearsal.mutation['round']}) is running in the background: nobody to remind"])
    role = _awaited_role(rehearsal, home)
    if role == "director":
        return _settle(rehearsal, Step("escalate", "waiting on the Director: answer the pending question with an `answer` message, from the director"), home, tools)
    if not role or role not in rehearsal.dispatches:
        return Step("wait", done=[f"nobody to remind: no worker of Rehearsal {rehearsal.id} is known to be awaited"])
    _remind(rehearsal, role, home, tools)
    return Step("wait", done=[f"the {role} reminded: Ballet was waiting for it"])


def _awaited_role(rehearsal, home):
    """Le rôle à qui la question en attente est adressée, sinon celui du dernier `handoff` du journal ; vide sans rien."""
    if rehearsal.pending:
        return rehearsal.pending[-1]["to"]
    handoffs = [entry for entry in _journal_of(rehearsal.id, home) if entry["event"] == "handoff"]
    return handoffs[-1]["detail"]["role"] if handoffs else ""


def _remind(rehearsal, role, home, tools):
    tools.orca(["orchestration", "send", "--to", f"dispatch:{rehearsal.dispatches[role]}",
                "--subject", f"{rehearsal.id} · {role}: Ballet is waiting for you", "--body", IDLE_REMINDER])
    _log_handoff(rehearsal, role, "nudge", IDLE_REMINDER, home)


def status_session(session_item, home, tools):
    """La Rehearsal en cours de la session et la session, ou, sans Rehearsal en cours, la session seule."""
    session = _load_session(session_item, home)
    if session.current:
        return status(session.current, home, tools)
    lines = _session_lines(session, "")
    if session.items:
        return Step("escalate", f"the session of {session.item} stopped before {session.items[0]}: fix it, then resume", lines)
    return Step("done", f"the session of {session.item} is over", lines)


# --- la session ---------------------------------------------------------------


def stop_session(item, reason, home, tools):
    """Maestro arrête le Conductor de l'élément (`ballet_launch.py stop`) : la Rehearsal en cours passe `escalated` (elle
    attend le Director ; son état, sa branche et son worktree sont gardés) et le Ballet status de l'issue le dit. Rend les
    dispatches de ses workers, que l'appelant arrête, et les lignes de ce qui a été fait ; sans session ouverte, rien."""
    session = next((open_ for open_ in open_sessions(home) if item in (open_.item.lstrip("#"), open_.issue)), None)
    if not session:
        return [], []
    dispatches = _escalate_current(session, reason, home)
    return dispatches, _follow_on_github(session.item, Step("escalate", reason), home, tools).done


def _escalate_current(session, reason, home):
    if not session.current or not _exists(session.current, home):
        return []
    rehearsal = load(session.current, home)
    if rehearsal.status == "open":
        rehearsal.status, rehearsal.reason = "escalated", reason
    _log(home, rehearsal, "stopped", {"reason": reason})
    _save(rehearsal, home)
    return list(rehearsal.dispatches.values())


def _new_session(item, config, tools):
    """La session d'un élément : son mode, l'approbation de son plan et son statut, lus sur son issue ; une feature
    sans issue part en `assisted`, et suit le profil pour son plan."""
    if FEATURE_ITEM.match(item):
        return _with_plan_approval(Session(item=item, items=[item]), "", config)
    fields = ballet_github.queue_fields(item, run=tools.gh)
    if fields["type"] not in QUEUED_TYPES:
        raise RehearsalError(_not_a_session_item(item, fields["type"]))
    mode, approval = _mode_and_approval(item, fields)
    session = Session(item=item, mode=mode, issue=item[1:], items=[item], ballet_status=fields["status"])
    return _with_plan_approval(session, approval, config)


def _mode_and_approval(item, fields):
    """Le mode et le champ `Plan approval` de l'issue, chacun parmi ses valeurs connues."""
    mode, approval = fields["mode"] or DEFAULT_MODE, fields["plan_approval"]
    if mode not in REHEARSAL_MODES:
        raise RehearsalError(f"{item}: unknown Rehearsal mode '{mode}'; known: {', '.join(REHEARSAL_MODES)}")
    if approval and approval not in PLAN_APPROVALS:
        raise RehearsalError(f"{item}: unknown Plan approval '{approval}'; known: {', '.join(PLAN_APPROVALS)}")
    return mode, approval


def _with_plan_approval(session, approval, config):
    """L'issue d'abord, puis le profil ; en autopilot, personne n'approuve."""
    if session.mode == AUTOPILOT:
        session.plan_approval, session.plan_approval_from = False, AUTOPILOT
    elif approval:
        session.plan_approval, session.plan_approval_from = PLAN_APPROVALS[approval], "issue"
    else:
        session.plan_approval, session.plan_approval_from = config["rehearsal"]["plan_approval"], "project"
    return session


def _plan_approval_line(session):
    choice = "required" if session.plan_approval else "skipped"
    return f"session of {session.item}: mode {session.mode}, plan approval {choice} ({session.plan_approval_from})"


def _not_a_session_item(item, issue_type):
    if issue_type == SLICE_TYPE:
        return f"{item} is a Slice: begin its Feature, its slices follow"
    kind = f"a {issue_type}" if issue_type else "an issue without a type"
    return f"{item} is {kind}: a session plays a Feature, a Bug or a Task; set its type on GitHub"


def _play_next(session_item, step, home, tools):
    """Ouvre la Rehearsal de l'élément suivant de la session ; plus rien à jouer, la session est finie ; si la
    Rehearsal ne peut pas s'ouvrir, la session s'arrête avant lui."""
    session = _load_session(session_item, home)
    session.current = ""
    if not session.items:
        session.status = "done"
        session.frictions = _frictions_of_played(session, home)
        _save_session(session, home)
        return Step(step.next, step.reason, step.done + [_session_done_line(session), *_friction_lines(session)])
    item = session.items.pop(0)
    _save_session(session, home)
    try:
        following = _begin(item, session, home, tools)
    except (RehearsalError, ballet_github.GitHubError) as error:
        _push_back(session_item, item, home)
        return Step("escalate", f"the session of {session.item} stopped before {item}: {error}; fix it, then resume", step.done)
    announced = [f"next in the session: {item}"] if session.played else []
    return Step(following.next, following.reason, step.done + announced + following.done)


def _after_premiere(rehearsal, step, home, tools):
    """La Premiere de la Rehearsal en cours de sa session ouvre la suivante, depuis `main`."""
    session = _session_of(rehearsal, home)
    if not session or session.current != rehearsal.id:
        return step
    return _play_next(session.item, step, home, tools)


def _session_first(rehearsal, items, planned, home):
    """Les slices d'un plan passent en tête de la session ; une feature y gagne son issue. Un plan amendé en review
    remplace celles de sa version précédente."""
    session = _load_session(rehearsal.session, home)
    session.items = items + [item for item in session.items if item not in rehearsal.queued]
    session.issue = session.issue or planned
    rehearsal.queued = items
    _save_session(session, home)


def _rename_in_session(rehearsal, previous, home):
    session = _load_session(rehearsal.session, home)
    session.current = rehearsal.id if session.current == previous else session.current
    for entry in session.played:
        if entry["rehearsal"] == previous:
            entry["rehearsal"] = rehearsal.id
    _save_session(session, home)


def _join_session(rehearsal, item, home):
    """La Rehearsal qui s'ouvre devient celle en cours de sa session."""
    session = _load_session(rehearsal.session, home)
    session.current = rehearsal.id
    session.played.append({"item": item, "rehearsal": rehearsal.id})
    _save_session(session, home)


def _push_back(session_item, item, home):
    session = _load_session(session_item, home)
    session.items.insert(0, item)
    _save_session(session, home)


def _refuse_if_in_session(item, home):
    """Un élément n'est joué que par une session à la fois, qu'on le nomme par sa feature ou par son issue."""
    number = item[1:] if item.startswith("#") else ""
    for session in open_sessions(home):
        if session.item == item or (number and session.issue == number):
            raise RehearsalError(f"{item} is already played by the session of {session.item} "
                                 "(in Ballet's base): resume it, or stop it")


def _follow_on_github(session_item, step, home, tools):
    """Le Ballet status de l'issue de la session suit chaque pas. Il n'est écrit que s'il change ; un refus de GitHub
    se dit, sans rien arrêter."""
    session = _load_session(session_item, home) if session_item and _session_exists(session_item, home) else None
    if session:
        step.item = session.item
    if not session or not session.issue:
        return step
    status = _ballet_status_of(step, session, home)
    if status == session.ballet_status:
        return step
    try:
        ballet_github.set_status(session.issue, status, run=tools.gh)
    except (RehearsalError, ballet_github.GitHubError) as error:
        step.done.append(f"Ballet status of #{session.issue} not set to {status}: {error}")
        return step
    session.ballet_status = status
    _save_session(session, home)
    step.done.append(f"Ballet status of #{session.issue}: {status}")
    return step


def _ballet_status_of(step, session, home):
    """`plan-review` tant que le plan est en review (la discussion comprise), `escalated` sur une autre escalade,
    `done` à la dernière Premiere, `in-rehearsal` sinon."""
    if step.next != "done" and _waits_for_its_plan(session, home):
        return "plan-review"
    if step.next == "escalate":
        return "escalated"
    if step.next == "done" and session.status == "done":
        return "done"
    return "in-rehearsal"


def _waits_for_its_plan(session, home):
    if not session.current or not _exists(session.current, home):
        return False
    return load(session.current, home).blocked_on == "plan"


def _session_lines(session, current):
    if not session:
        return []
    playing = f"playing {current}; " if current else ""
    lines = [f"session of {session.item} (mode {session.mode}): {playing}next: {', '.join(session.items) or 'nothing'}"]
    if session.played:
        lines.append("played: " + ", ".join(f"{entry['rehearsal']} ({entry['item']})" for entry in session.played))
    return lines


def _record_frictions(rehearsal, home):
    """À la fin de la Rehearsal, ses frictions : dans son état et au journal, pour la Scène et le `done` de la session."""
    rehearsal.frictions = ballet_frictions.of_rehearsal(asdict(rehearsal), _journal_of(rehearsal.id, home))
    _save(rehearsal, home)
    _log(home, rehearsal, "frictions", rehearsal.frictions)


def _frictions_of_played(session, home):
    played = [entry["rehearsal"] for entry in session.played]
    return {rehearsal_id: load(rehearsal_id, home).frictions for rehearsal_id in played if _exists(rehearsal_id, home)}


def _friction_lines(session):
    return [ballet_frictions.line(rehearsal_id, record) for rehearsal_id, record in session.frictions.items()]


def _journal_of(rehearsal_id, home):
    return ballet_store.journal_of(home, ballet_store.REHEARSAL, rehearsal_id)


def _session_done_line(session):
    return f"session of {session.item} done: " + (", ".join(entry["rehearsal"] for entry in session.played) or "nothing played")


# --- les transitions ----------------------------------------------------------


def _handle(rehearsal, header, text, question_id, config, home, tools):
    _log(home, rehearsal, "message", {**header, "text": text})
    rehearsal.nudges.pop(header["from"], None)
    return _route(rehearsal, header, text, question_id, config, home, tools)


def _route(rehearsal, header, text, question_id, config, home, tools):
    _count_round(rehearsal, header, config)
    kind, sender = header["type"], header["from"]
    if _in_plan_review(rehearsal, header):
        return _plan_review(rehearsal, header, text, config, home, tools)
    if kind in ("revise", "approve"):
        raise RehearsalError(f"a `{kind}` message answers a plan in review, and no plan waits for the Director")
    if kind == "question":
        return _relay_question(rehearsal, header, text, question_id, config, home, tools)
    if kind == "answer":
        return _relay_answer(rehearsal, header, text, config, home, tools)
    if kind == "report" and sender == "choreographer" and rehearsal.dancer_start:
        return _misplaced_report(rehearsal, sender, config, home, tools)
    if kind == "report" and sender == "choreographer":
        return _after_plan(rehearsal, text, config, home, tools)
    if kind == "report" and sender == "dancer":
        return _after_code(rehearsal, text, config, home, tools)
    if kind == "verdict" and sender == "critic":
        return _after_verdict(rehearsal, verdict_of(text), text, config, home, tools)
    if kind == "escalation":
        return Step("escalate", f"{sender} escalates: see its message")
    raise RehearsalError(f"no transition for a {kind} from the {sender}")


def _worker_stopped(rehearsal, message, home, tools):
    """Un worker a fini son tour sans `worker_done` : relancé pour envoyer son rapport, une fois ; ensuite, ou s'il
    est tombé en erreur, c'est au Director."""
    payload = ballet_orca.payload(message)
    role = _worker_role(rehearsal, message)
    if not role or payload.get("stopReason") != "finished" or rehearsal.nudges.get(role, 0) >= MAX_NUDGES:
        raise RehearsalError(f"Orca: {message.get('subject', 'a worker stopped')}: {message.get('body', '')[:300]}")
    rehearsal.nudges[role] = rehearsal.nudges.get(role, 0) + 1
    tools.orca(["orchestration", "send", "--to", f"dispatch:{rehearsal.dispatches[role]}",
                "--subject", f"{rehearsal.id} · {role}: send your worker_done", "--body", REPORT_REMINDER])
    _log_handoff(rehearsal, role, "nudge", REPORT_REMINDER, home)
    return Step("wait", done=[f"the {role} ended its turn without worker_done: asked to send its report"])


def _relay_question(rehearsal, header, text, question_id, config, home, tools):
    """Publie la question sur l'issue, puis la porte au rôle qui doit répondre ; le demandeur attend, éveillé."""
    if not question_id:
        raise RehearsalError("a question needs the Orca message id (--question) to send the answer back")
    step = Step("wait", done=[_publish_exchange(rehearsal, "question", text, home, tools)])
    to = "director" if header["to"] in ("director", "conductor") else header["to"]
    if to != "director" and header["from"] in ANSWERING_ROLES:
        found = _verified_and_owned(rehearsal, header["from"], config, home, tools)
        if found:
            return Step("escalate", f"policy: the {header['from']} broke the rules before asking: {'; '.join(found)}", step.done)
    rehearsal.pending.append({"id": question_id, "from": header["from"], "to": to})
    if to == "director":
        return Step("escalate", _for_the_director(header), step.done)
    _ask_role(rehearsal, header["to"], f"Rehearsal {rehearsal.id}, {_target(rehearsal)}, branch `{rehearsal.branch}`. "
              f"Answer this question from the {header['from']}, then return your answer "
              f"as a Ballet message (`type: answer`, to the {header['from']}):\n\n{text}", config, home, tools)
    step.done.append(f"question carried to the {header['to']}")
    return step


def _for_the_director(header):
    """Le Conductor ne fait que relayer : une question qui lui est adressée va au Director."""
    asked = "the Conductor, who only relays" if header["to"] == "conductor" else "the Director"
    return f"the {header['from']} asks {asked}: answer with an `answer` message, from the director"


def _relay_answer(rehearsal, header, text, config, home, tools):
    """Publie la réponse sur l'issue et la rend au demandeur, qui reprend avec son contexte."""
    question = _pending_question(rehearsal, asker=header["to"], answerer=header["from"])
    if header["from"] in ANSWERING_ROLES:
        found = _verified_and_owned(rehearsal, header["from"], config, home, tools)
        if found:
            return Step("escalate", f"policy: the {header['from']} broke the rules while answering: {'; '.join(found)}")
    step = Step("wait", done=[_publish_exchange(rehearsal, "answer", text, home, tools)])
    tools.orca(["orchestration", "reply", "--id", question["id"], "--body", text])
    _log_handoff(rehearsal, header["to"], "reply", text, home)
    rehearsal.pending.remove(question)
    step.done.append(f"answer handed back to the {header['to']}")
    return step


def _misplaced_report(rehearsal, role, config, home, tools):
    """Un `report` du Choreographer une fois le Dancer lancé : son plan est déjà joué. Avec une question en attente, c'est sa
    réponse mal typée ; sinon rien ne lui était demandé. Renvoyé une fois sans passer par la politique (le worktree porte
    alors le travail en cours du Dancer, qui n'est pas le sien) et sans rien replanifier ; la deuxième fois, escalade."""
    rehearsal.misplaced[role] = rehearsal.misplaced.get(role, 0) + 1
    if rehearsal.misplaced[role] > MAX_MISPLACED:
        return Step("escalate", f"the {role} sent a report again while the Dancer has the branch: see its message")
    question = next((pending for pending in rehearsal.pending if pending["to"] == role), None)
    body = _answer_expected(question) if question else NOTHING_ASKED
    tools.orca(["orchestration", "send", "--to", f"dispatch:{rehearsal.dispatches[role]}",
                "--subject", f"{rehearsal.id} · {role}: message not expected", "--body", body])
    _log_handoff(rehearsal, role, "send", body, home)
    expected = f"an answer to the {question['from']}" if question else "nothing"
    return Step("wait", done=[f"the {role} sent a report while the Dancer has the branch: sent back, {expected} expected, "
                              "nothing replanned, no policy check"])


def _answer_expected(question):
    return (f"Your plan is already being played: Ballet expects no report from you now. The {question['from']} asked you a question: "
            f"answer it with one Ballet message `type: answer`, `from: choreographer`, `to: {question['from']}`, point by point, "
            "as your worker_done. Do not touch the worktree's uncommitted files: they are the Dancer's work in progress.")


NOTHING_ASKED = ("Your plan is already being played and nothing is asked of you: Ballet expects no report from you now. "
                 "Do not touch the worktree: its uncommitted files are the Dancer's work in progress. Stay idle.")


def _after_plan(rehearsal, report, config, home, tools):
    """La politique d'abord. Puis le plan est lu sur GitHub : l'issue seule, ou ses slices, prennent la tête de la file ;
    la première se joue dans ce worktree, avec les commits du Choreographer. En review, le Director l'approuve d'abord."""
    found = _policy(rehearsal, "choreographer", config, home, tools)
    if found:
        return _refused_by_policy(rehearsal, "choreographer", found, config, home, tools)
    _own_commits(rehearsal, tools)
    planned, issues = _planned_issues(rehearsal, report, tools)
    step = Step("wait", done=[_plan_line(planned, issues)])
    step.done += _hand_over(rehearsal, planned, issues[0], home, tools)
    _session_first(rehearsal, [f"#{number}" for number, _, _ in issues[1:]], planned, home)
    if rehearsal.plan == "review":
        return _await_plan_approval(rehearsal, planned, step)
    return _dancer_on_the_plan(rehearsal, step, config, home, tools)


def _planned_issues(rehearsal, report, tools):
    """L'issue planifiée (celle du rapport, ou celle de la Rehearsal) et ce qui se joue : ses slices, sinon elle seule.
    Chacune doit avoir les tâches de son plan."""
    if _report_field(report, "Outcome") == "blocked":
        raise RehearsalError("the Choreographer is blocked: see its report")
    planned = _report_issue(report) or rehearsal.issue
    if not planned:
        raise RehearsalError("the Choreographer reported no issue: its report needs `- Issue: #<n>`")
    numbers = ballet_github.slices_of(planned, run=tools.gh) or [planned]
    issues = [(number, *_issue(number, tools)) for number in numbers]
    without_tasks = [f"#{number}" for number, _, body in issues if not _has_tasks(body)]
    if without_tasks:
        raise RehearsalError(f"the Choreographer reported, but {', '.join(without_tasks)} has no tasks in its plan")
    return planned, issues


def _hand_over(rehearsal, planned, first, home, tools):
    """La Rehearsal joue la première issue du plan. Si c'est une slice, la planification lui laisse son worktree :
    la branche prend le nom de la slice, les commits du Choreographer restent à son nom (`owned`). La planification
    reste dans l'état, terminée, sur l'issue planifiée ; la slice la nomme (`planned_by`) : la Scène relie leurs fils."""
    number, title, _ = first
    rehearsal_id = _rehearsal_id(title)
    if rehearsal_id == rehearsal.id:
        rehearsal.issue = number
        return []
    previous, old_branch = rehearsal.id, rehearsal.branch
    _refuse_if_already_open(Rehearsal(id=rehearsal_id, issue=number, repo=rehearsal.repo), home)
    _save(Rehearsal(**{**asdict(rehearsal), "issue": planned, "status": "done", "reason": f"planned: its worktree plays {rehearsal_id}"}), home)
    _log(home, rehearsal, "handover", {"to": rehearsal_id, "issue": number, "planned": planned})
    git = tools.git(rehearsal.worktree)
    git(["branch", "-m", old_branch, f"rehearsal/{rehearsal_id}"])
    rehearsal.id, rehearsal.issue, rehearsal.planned_by = rehearsal_id, number, previous
    rehearsal.refs = ballet_policy.refs(git)
    _rename_in_session(rehearsal, previous, home)
    return [f"now playing: Rehearsal {rehearsal_id} (issue #{number}) in the worktree of {previous}, branch {rehearsal.branch}"]


def _await_plan_approval(rehearsal, planned, step):
    rehearsal.blocked_on, rehearsal.plan_issue = "plan", planned
    return Step("escalate", _plan_to_review(planned), step.done)


def _plan_to_review(planned):
    return (f"plan to review: read #{planned} and its slices, then write to the choreographer: "
            "a `question`, a `revise` with your remarks, or `approve` (receive)")


# --- la review du plan --------------------------------------------------------


def _in_plan_review(rehearsal, header):
    """Un plan en review : ce que le Director écrit au Choreographer, et la réponse du Choreographer au Director."""
    if rehearsal.blocked_on != "plan":
        return False
    from_the_director = header["from"] == "director" and header["type"] in PLAN_REVIEW_MESSAGES
    to_the_director = header["from"] == "choreographer" and header["to"] == "director" and header["type"] == "answer"
    return from_the_director or to_the_director


def _plan_review(rehearsal, header, text, config, home, tools):
    """La review du plan, une discussion : le Director questionne le Choreographer, lui demande d'amender son plan, ou
    l'approuve. Chaque échange est publié sur l'issue planifiée ; le plan reste en review jusqu'à `approve`."""
    if header["from"] == "choreographer":
        return _choreographer_answers_the_director(rehearsal, text, config, home, tools)
    if header["to"] != "choreographer":
        raise RehearsalError(f"in a plan review, the Director writes to the choreographer, not to the {header['to']}")
    published = _publish_on_the_plan(rehearsal, header["type"], text, home, tools)
    if header["type"] == "approve":
        return _plan_approved(rehearsal, published, config, home, tools)
    _ask_role(rehearsal, "choreographer", _plan_review_assignment(rehearsal, header["type"], text), config, home, tools)
    return Step("wait", done=[published, f"{header['type']} carried to the choreographer"])


def _choreographer_answers_the_director(rehearsal, text, config, home, tools):
    """Une réponse ne touche ni au plan ni à la branche : la politique le vérifie, puis la review reprend."""
    found = _verified_and_owned(rehearsal, "choreographer", config, home, tools)
    if found:
        return Step("escalate", f"policy: the choreographer broke the rules while answering: {'; '.join(found)}")
    published = _publish_on_the_plan(rehearsal, "answer", text, home, tools)
    return Step("escalate", _plan_to_review(rehearsal.plan_issue), [published, "the choreographer answers the Director"])


def _plan_approved(rehearsal, published, config, home, tools):
    rehearsal.blocked_on = ""
    _log(home, rehearsal, "director-decision", {"plan": rehearsal.plan_issue, "approved": True})
    step = Step("wait", done=[published, f"the Director approves the plan of #{rehearsal.plan_issue}"])
    return _dancer_on_the_plan(rehearsal, step, config, home, tools)


def _plan_review_assignment(rehearsal, kind, text):
    planned = rehearsal.plan_issue
    if kind == "question":
        return (f"The Director reviews your plan of #{planned} and asks you. Answer as a Ballet message (`type: answer`, "
                f"to the director, subject `#{planned}`), point by point, without changing the plan nor the branch:\n\n{text}")
    return (f"The Director reviews your plan of #{planned} and asks for changes. Take them in the plan (`plan`) and in "
            "the slices (`plan <slice>` to rewrite one, `slice` to add one; a slice to drop: say so, the Director closes "
            "it), add a line to *Amendments*, commit on this branch what changes in your ADRs and rules, then report "
            f"again, with `- Issue: #{planned}`:\n\n{text}")


def _publish_on_the_plan(rehearsal, what, text, home, tools):
    ballet_github.comment_issue(rehearsal.plan_issue, _outbox(text, home), run=tools.gh)
    return f"{what} published on issue #{rehearsal.plan_issue}"


def _dancer_on_the_plan(rehearsal, step, config, home, tools):
    _ask_role(rehearsal, "dancer", _first_assignment("dancer", rehearsal, config), config, home, tools)
    step.done.append(f"dancer started on issue #{rehearsal.issue}")
    return step


def _plan_line(planned, issues):
    if [number for number, _, _ in issues] == [planned]:
        return f"plan found on issue #{planned}"
    return f"issue #{planned} cut into slices: " + ", ".join(f"#{number}" for number, _, _ in issues)


def _after_code(rehearsal, report, config, home, tools):
    """Le rapport d'abord (une ligne `Red:` par tâche faite), puis la politique et la preuve : rien n'est poussé en
    violation ni rouge. La preuve verte, la branche part au Critic, et la mutation en arrière-plan, en même temps."""
    rehearsal.renamed_tests.update(_declared_renames(report))
    without_red = _tasks_without_red(report)
    if without_red:
        return _refused_report(rehearsal, without_red, config, home, tools)
    found = _policy(rehearsal, "dancer", config, home, tools)
    if found:
        return _refused_by_policy(rehearsal, "dancer", found, config, home, tools)
    return _proven_then_mutated(rehearsal, report, config, home, tools)


def _proven_then_mutated(rehearsal, report, config, home, tools):
    """La preuve, puis, en même temps, la mutation de ce qui a changé depuis la dernière mutation verte (en arrière-plan)
    et la branche au Critic : le verdict et la mutation décident ensemble."""
    proof = _prove(rehearsal, config, home, tools)
    if not proof.passed:
        return _refused_by_proof(rehearsal, proof, config, home, tools)
    rehearsal.held_verdict, rehearsal.mutation_red = {}, []
    step = Step("wait", done=[_proof_line(proof), _start_mutation(rehearsal, config, home, tools)])
    return _publish_code(rehearsal, report, step, config, home, tools)


def _tasks_without_red(report):
    """Les tâches cochées du rapport sans leur ligne `Red:` (le test et son échec, vus avant le code)."""
    missing, task, seen_red = [], None, False
    for line in report.splitlines() + ["- end"]:
        if task and RED_LINE.match(line.strip()):
            seen_red = True
        elif _starts_an_item(line):
            if task and not seen_red:
                missing.append(task)
            task, seen_red = _done_task(line), False
    return missing


def _starts_an_item(line):
    """Une tâche, ou une ligne du premier niveau du rapport (`- Proof:`, un titre) : la tâche d'avant est finie."""
    return bool(TASK_LINE.match(line.strip())) or line.startswith(("- ", "#"))


def _done_task(line):
    found = TASK_LINE.match(line.strip())
    return found.group(2) if found and found.group(1) in "xX" else None


def _declared_renames(report):
    """Les tests que le Dancer déclare renommés : `- Renamed test: <ancien> → <nouveau>`."""
    return {match.group(1).strip("` "): match.group(2).strip("` ") for match in RENAMED_TEST.finditer(report)}


def _refused_report(rehearsal, without_red, config, home, tools):
    """Un rapport sans le rouge d'une tâche n'est pas reçu : rien n'est lancé ; une seconde fois, escalade."""
    rehearsal.refused_reports += 1
    listed = "; ".join(without_red)
    if rehearsal.refused_reports > MAX_POLICY_RESENDS:
        return Step("escalate", f"the Dancer's report has no `Red:` line again for: {listed}")
    _ask_role(rehearsal, "dancer", _red_fix_assignment(without_red), config, home, tools)
    return Step("wait", done=[f"Dancer report refused, nothing run: no `Red:` line for {listed}"])


def _publish_code(rehearsal, report, step, config, home, tools):
    """Pousse la branche, ouvre la PR au premier rapport, y publie le rapport, mesure le diff et passe la main au Critic."""
    ballet_github.push_branch(rehearsal.branch, git=tools.git(rehearsal.repo))
    step.done.append(f"{rehearsal.branch} pushed")
    if rehearsal.pull_request:
        step.done.append(_resolve_fixed_points(rehearsal, report, home, tools))
    else:
        rehearsal.pull_request = ballet_github.open_pull_request(rehearsal.issue, rehearsal.branch, run=tools.gh)
        step.done.append(f"pull request #{rehearsal.pull_request} opened")
    _comment_pull_request(rehearsal, report, home, tools)
    step.done.append(f"Dancer report published on #{rehearsal.pull_request}")
    size = _measure(rehearsal, config, home, tools)
    step.done.append(_size_line(rehearsal))
    if _blocked_by_size(rehearsal, size, config, tools):
        rehearsal.blocked_on = "size"
        return Step("escalate", f"diff of {size.counted} lines, over max_diff_lines ({config['escalation']['max_diff_lines']}) "
                    f"in strict mode: label #{rehearsal.pull_request} ballet:size-accepted, or ballet:rejected with a comment, "
                    "then resume", step.done)
    return _to_the_critic(rehearsal, step, config, home, tools)


def _file_notes(rehearsal, text, step, tools):
    """Les notes d'une approbation vont dans l'issue de dette technique du projet, pas au Dancer. Elles ne bloquent
    jamais : un refus de GitHub n'est qu'une ligne du pas, la Premiere a lieu."""
    notes = notes_of(text)
    if not notes:
        return
    try:
        number, created = ballet_github.file_technical_debt(rehearsal.pull_request, rehearsal.id, notes, run=tools.gh)
    except ballet_github.GitHubError as error:
        step.done.append(f"{len(notes)} note(s) of the Critic not filed in technical debt: {error}")
        return
    rehearsal.notes = f"#{number}"
    where = f"new technical debt issue #{number} (proposed)" if created else f"technical debt issue #{number}"
    step.done.append(f"{len(notes)} note(s) of the Critic filed in {where}")


def _to_the_critic(rehearsal, step, config, home, tools):
    _ask_role(rehearsal, "critic", _critic_assignment(rehearsal, config), config, home, tools)
    step.done.append(f"critic asked to review #{rehearsal.pull_request}, round {_review_round(rehearsal)}")
    return step


def _measure(rehearsal, config, home, tools):
    """Compte le diff de la branche, le note sur la PR (`ballet:oversized`) et le journalise, à chaque fois :
    sans les mesures sous le seuil, pas de taux de dépassement."""
    escalation = config["escalation"]
    size = ballet_size.branch_size(rehearsal.branch, escalation["diff_exclude"], tools.git(rehearsal.repo))
    over = size.over(escalation["max_diff_lines"])
    ballet_github.mark_size(rehearsal.pull_request, over, run=tools.gh)
    rehearsal.size = {"counted": size.counted, "excluded": size.excluded, "excluded_files": size.excluded_files,
                      "limit": escalation["max_diff_lines"], "strict": escalation["max_diff_strict"], "over": over,
                      "round": rehearsal.round_trips + 1}
    _log(home, rehearsal, "diff-size", rehearsal.size)
    return size


def _blocked_by_size(rehearsal, size, config, tools):
    escalation = config["escalation"]
    if not escalation["max_diff_strict"] or not size.over(escalation["max_diff_lines"]):
        return False
    return not ballet_github.size_accepted(rehearsal.pull_request, run=tools.gh)


def _after_verdict(rehearsal, verdict, text, config, home, tools):
    found = _policy(rehearsal, "critic", config, home, tools)
    if found:
        return _refused_by_policy(rehearsal, "critic", found, config, home, tools)
    step = Step("wait")
    _publish_review(rehearsal, text, home, tools)
    ballet_github.update_verdicts(rehearsal.pull_request, run=tools.gh)
    _label(rehearsal, verdict, tools)
    step.done.append(f"verdict {verdict} published on #{rehearsal.pull_request}, labelled, Verdicts comment updated")
    if verdict == "ESCALATE":
        return Step("escalate", "the Critic escalates: see its review", step.done)
    rehearsal.reviews = max(rehearsal.reviews, rehearsal.round_trips) + 1
    if rehearsal.mutation:
        rehearsal.held_verdict = {"verdict": verdict, "text": text}
        step.done.append(f"verdict {verdict} held until the mutation (round {rehearsal.mutation['round']}) is done")
        return step
    return _decide(rehearsal, verdict, text, _held_red(rehearsal), step, config, home, tools)


def _decide(rehearsal, verdict, text, red, step, config, home, tools):
    """Le verdict du Critic et la mutation, ensemble : approuvé et verte, les notes vont en dette technique puis la
    Premiere ; sinon le Dancer reprend, en un seul tour, avec les points du Critic et les survivants de la mutation."""
    if red:
        rehearsal.red_mutations += 1
        if rehearsal.red_mutations > config["escalation"]["max_round_trips"]:
            names = ", ".join(outcome.tool for outcome in red)
            return Step("escalate", f"mutation: red {rehearsal.red_mutations} times, over max_round_trips ({names})", step.done)
    if verdict == "APPROVED" and not red:
        _file_notes(rehearsal, text, step, tools)
        return _then_premiere(rehearsal, step, config, tools)
    if verdict == "REJECTED":
        rehearsal.round_trips += 1
        if rehearsal.round_trips > config["escalation"]["max_round_trips"]:
            return Step("escalate", f"{rehearsal.round_trips} rejections, over max_round_trips", step.done)
    else:
        _label(rehearsal, "REJECTED", tools)
    _ask_role(rehearsal, "dancer", _fix_assignment(rehearsal, verdict, red, config), config, home, tools)
    step.done.append(_fix_line(rehearsal, verdict, red, config))
    return step


def _fix_line(rehearsal, verdict, red, config):
    """Ce que le Dancer reprend, en une ligne : les points du Critic, les survivants, ou les deux."""
    names = ", ".join(outcome.tool for outcome in red)
    mutation = f"mutation red ({names}, {rehearsal.red_mutations}/{config['escalation']['max_round_trips']})" if red else ""
    if verdict == "APPROVED":
        return f"approved, but {mutation}: ballet:rejected, dancer asked to kill the survivors, then the Critic reviews again"
    with_mutation = f" and {mutation}" if red else ""
    return f"dancer asked to fix the Critic's points{with_mutation}, round {_review_round(rehearsal)}"


def _held_red(rehearsal):
    """Les outils rouges d'une mutation finie avant le verdict, rendus une seule fois."""
    red = [ballet_mutation.Outcome(**outcome) for outcome in rehearsal.mutation_red]
    rehearsal.mutation_red = []
    return red


def _apply_decision(rehearsal, config, home, tools):
    """`ballet:approved` : la Premiere ; `ballet:rejected` : le Dancer reprend avec les commentaires du Director.
    Un plan en review ne se reprend pas : il attend un message du Director."""
    if rehearsal.blocked_on == "plan":
        return Step("escalate", _plan_to_review(rehearsal.plan_issue))
    if not rehearsal.pull_request:
        raise RehearsalError("no pull request yet: answer the pending question with an `answer` message (receive)")
    decision = ballet_github.director_decision(rehearsal.pull_request, run=tools.gh)
    if rehearsal.blocked_on == "size":
        decision["size_accepted"] = ballet_github.size_accepted(rehearsal.pull_request, run=tools.gh)
    _log(home, rehearsal, "director-decision", decision)
    if decision["verdict"] == "APPROVED" and rehearsal.mutation:
        return Step("escalate", f"the mutation (round {rehearsal.mutation['round']}) is still running on #{rehearsal.pull_request}: "
                    "resume once it is done")
    if decision["verdict"] == "APPROVED":
        rehearsal.label, rehearsal.blocked_on, rehearsal.mutation_red = "APPROVED", "", []
        return _premiere(rehearsal, config, tools)
    if decision["verdict"] == "REJECTED":
        return _back_to_the_dancer(rehearsal, decision["comments"], config, home, tools)
    if decision.get("size_accepted"):
        rehearsal.blocked_on = ""
        return _to_the_critic(rehearsal, Step("wait", done=[f"the Director accepts the size of #{rehearsal.pull_request}"]),
                              config, home, tools)
    size_option = "ballet:size-accepted to send it to the Critic, " if rehearsal.blocked_on == "size" else ""
    return Step("escalate", f"nothing decided yet on #{rehearsal.pull_request}: label it {size_option}ballet:approved, "
                "or ballet:rejected with a comment saying what to fix, then resume")


def _back_to_the_dancer(rehearsal, comments, config, home, tools):
    if not comments:
        return Step("escalate", f"ballet:rejected needs a comment on #{rehearsal.pull_request} saying what to fix, then resume")
    rehearsal.label, rehearsal.blocked_on = "REJECTED", ""
    red = _held_red(rehearsal)
    _ask_role(rehearsal, "dancer", _director_fix_assignment(rehearsal, comments, red, config), config, home, tools)
    with_mutation = " with the mutation's survivors" if red else ""
    return Step("wait", done=[f"the Director rejected #{rehearsal.pull_request}: {len(comments)} comment(s) carried to the dancer{with_mutation}"])


def _policy(rehearsal, role, config, home, tools, answering=False):
    """Les violations du passage qui s'achève, journalisées à chaque fois ; en règle, ses branches font foi."""
    git = tools.git(rehearsal.worktree)
    passage = ballet_policy.Passage(role, rehearsal.branch, rehearsal.checkpoint, rehearsal.refs, rehearsal.owned, answering,
                                    rehearsal.dancer_start, rehearsal.base, rehearsal.renamed_tests)
    found = ballet_policy.violations(passage, ballet_policy.policy_of(config), git)
    _log(home, rehearsal, "policy", {"role": role, "violations": found})
    if not found:
        rehearsal.refs = ballet_policy.refs(git)
    return found


def _refused_by_policy(rehearsal, role, found, config, home, tools):
    """Le rôle corrige une fois ; la deuxième violation escalade. Le Critic, en lecture seule, n'a rien à corriger."""
    rehearsal.violations[role] = rehearsal.violations.get(role, 0) + 1
    listed = "; ".join(found)
    if role == "critic" or rehearsal.violations[role] > MAX_POLICY_RESENDS:
        return Step("escalate", f"policy: the {role} broke the rules: {listed}")
    _ask_role(rehearsal, role, _policy_fix_assignment(found), config, home, tools)
    return Step("wait", done=[f"policy refused the {role}'s work, sent back once: {listed}"])


def _prove(rehearsal, config, home, tools):
    """Lance la preuve du repo dans le worktree, journalisée à son début (`proof-start`) et à sa fin (`proof-end`,
    avec son statut et sa durée) ; une preuve qui salit le worktree n'est pas verte. Déjà verte sur ce commit, elle
    ne repasse pas (`proof-reused`). Une seule preuve à la fois par projet (OPP-84) : les Rehearsals en parallèle se
    disputent le port du serveur de dev et `target/`, la seconde attend (`proof-waiting`) que la première rende le verrou."""
    command, head = _proof_command(config), ballet_policy.head(tools.git(rehearsal.worktree))
    if head == rehearsal.proven:
        _log(home, rehearsal, "proof-reused", {"command": command, "head": head})
        return Proof(True, reused=True)
    with _proof_lock(home, rehearsal, command):
        _log(home, rehearsal, "proof-start", {"command": command, "head": head})
        started = time.monotonic()
        proof = tools.prove(command, rehearsal.worktree, config["escalation"]["proof_timeout_seconds"])
        seconds = round(time.monotonic() - started)
    dirty = ballet_policy.dirty_files(tools.git(rehearsal.worktree)) if proof.passed else []
    if dirty:
        proof = Proof(False, "The proof left the worktree dirty:\n" + "\n".join(dirty))
    _log(home, rehearsal, "proof-end", {"passed": proof.passed, "timed_out": proof.timed_out, "head": head,
                                        "seconds": seconds})
    if proof.passed:
        rehearsal.proven = head
    return proof


@contextlib.contextmanager
def _proof_lock(home, rehearsal, command):
    """Le verrou exclusif de preuve du projet (`proof.lock`, dans son dossier de travail) : pris sans attendre quand il
    est libre, sinon `proof-waiting` au journal puis attente ; rendu à la sortie, même sur une erreur."""
    with open(_run_dir(home) / PROOF_LOCK, "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _log(home, rehearsal, "proof-waiting", {"command": command})
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _proof_line(proof):
    return "proof already green on this commit: not run again" if proof.reused else "proof green"


def _refused_by_proof(rehearsal, proof, config, home, tools):
    """Rouge : le Dancer reprend avec la fin de la sortie, le Critic n'est pas mobilisé ; trop long ou trop souvent, escalade."""
    command = _proof_command(config)
    if proof.timed_out:
        return Step("escalate", f"proof: `{command}` still running after {config['escalation']['proof_timeout_seconds']}s "
                    "(proof_timeout_seconds)")
    rehearsal.red_proofs += 1
    if rehearsal.red_proofs > config["escalation"]["max_round_trips"]:
        return Step("escalate", f"proof: `{command}` red {rehearsal.red_proofs} times, over max_round_trips")
    _ask_role(rehearsal, "dancer", _proof_fix_assignment(command, proof), config, home, tools)
    return Step("wait", done=[f"proof red, nothing pushed: dancer asked to fix it ({rehearsal.red_proofs}/"
                              f"{config['escalation']['max_round_trips']})"])


def _proof_command(config):
    return next(iter(config["repos"].values()))["proof"]


# --- la mutation --------------------------------------------------------------


def _mutated_tools(rehearsal, config, tools):
    """Les outils de mutation que la branche touche, chacun avec son périmètre ; aucun si le profil la coupe."""
    declared = _mutation_tools(config)
    if not config["mutation"]["enabled"] or not declared:
        return []
    return ballet_mutation.scopes_of(declared, tools.git(rehearsal.worktree), since=rehearsal.mutated)


def _skip_mutation(rehearsal, config, home):
    """Le nœud sauté se dit au journal (`mutation-skipped`), avec sa raison."""
    if not config["mutation"]["enabled"]:
        reason = "disabled in the profile"
    elif not _mutation_tools(config):
        reason = "no mutation tool in the profile"
    elif rehearsal.mutated:
        reason = f"nothing changed for a mutation tool since the last green mutation ({rehearsal.mutated[:7]})"
    else:
        reason = "the diff touches no mutation tool"
    _log(home, rehearsal, "mutation-skipped", {"reason": reason})
    return f"mutation skipped: {reason}"


def _start_mutation(rehearsal, config, home, tools):
    """La mutation de ce qui a changé depuis la dernière verte, lancée en arrière-plan ; sinon le nœud sauté. Rend sa ligne."""
    scoped = _mutated_tools(rehearsal, config, tools)
    if not scoped:
        return _skip_mutation(rehearsal, config, home)
    return _launch_mutation(rehearsal, scoped, home, tools)


def _launch_mutation(rehearsal, scoped, home, tools, whole=False):
    """Trop long pour un appel du Conductor : la mutation part en arrière-plan, et le réveille par Orca à sa fin.
    `whole` : elle porte sur toute la branche, pas seulement sur ce qui a changé depuis la dernière verte. Rend sa ligne."""
    rehearsal.mutations += 1
    rehearsal.mutation = {"round": rehearsal.mutations, "head": ballet_policy.head(tools.git(rehearsal.worktree)),
                          "run": _conductor_run(rehearsal, tools), "started": _now(), "whole": whole}
    _save(rehearsal, home)
    tools.launch([sys.executable, str(Path(__file__).resolve()), "mutate", rehearsal.id], str(Path(home).resolve()), _run_dir(home))
    names = ", ".join(tool.name for tool, _ in scoped)
    return (f"mutation started in the background ({names}, round {rehearsal.mutations}), alongside the Critic: "
            "it wakes the Conductor when it is done")


def _mutate_each_tool(rehearsal, config, home, tools):
    """Le même chemin que `ballet_mutation.py run`, journalisé dans la Rehearsal (`mutation-start`, `mutation-end`)."""
    git = tools.git(rehearsal.worktree)
    since = "" if rehearsal.mutation.get("whole") else rehearsal.mutated
    scoped = ballet_mutation.scopes_of(_mutation_tools(config), git, since=since)
    folder, prefix = _run_dir(home) / rehearsal.id, f"mutation-{rehearsal.mutation['round']}"

    def journal(event, detail):
        _log(home, rehearsal, event, detail)
    return ballet_mutation.run_tools(scoped, rehearsal.worktree, folder, prefix, config["mutation"]["timeout_seconds"], git,
                                     journal, tools.mutate)


def _wake_the_conductor(rehearsal, home, tools):
    """Un message Orca au Run des workers : son coordinateur, le Conductor, est réveillé comme par un worker."""
    pending = rehearsal.mutation
    payload = {"ballet": "mutation", "rehearsal": rehearsal.id, "round": pending["round"]}
    try:
        tools.orca(["orchestration", "send", "--to", f"run:{pending['run']}", "--type", "status",
                    "--subject", f"{rehearsal.id} · mutation done", "--payload", json.dumps(payload),
                    "--body", f"The mutation of Rehearsal {rehearsal.id} (round {pending['round']}) is done: "
                              f"run `ballet_rehearsal.py receive {rehearsal.id} --run {pending['run']}`.", "--json"])
        _log(home, rehearsal, "mutation-wake", {"round": pending["round"], "sent": True})
    except RehearsalError as error:
        _log(home, rehearsal, "mutation-wake", {"round": pending["round"], "sent": False, "error": str(error)})


def _after_mutation(rehearsal, round_, config, home, tools):
    """La fin de la mutation : le code de sortie de chaque outil décide, avec le verdict du Critic (`_mutation_known`) ;
    trop longue, en panne, ou sur un worktree qui a bougé, escalade."""
    pending = rehearsal.mutation
    if not pending or round_ != pending["round"]:
        return Step("wait", done=[f"mutation wake for round {round_} ignored: no such mutation is running"])
    path = _mutation_results_path(rehearsal, home)
    if not path.is_file():
        return Step("wait", done=[f"mutation of round {round_} still running: no results yet in {path}"])
    results = json.loads(path.read_text(encoding="utf-8"))
    rehearsal.mutation = {}
    if "error" in results:
        return Step("escalate", f"mutation: the background run failed: {results['error']}")
    moved = ballet_policy.head(tools.git(rehearsal.worktree))
    if moved != pending["head"]:
        return Step("escalate", f"mutation: the worktree moved during the mutation ({pending['head']} → {moved})")
    outcomes = [ballet_mutation.Outcome(**outcome) for outcome in results["outcomes"]]
    late = [outcome.tool for outcome in outcomes if outcome.timed_out]
    if late:
        return Step("escalate", f"mutation: {', '.join(late)} still running after {config['mutation']['timeout_seconds']}s "
                    "([mutation] timeout_seconds)")
    red = [outcome for outcome in outcomes if not outcome.passed]
    if red:
        return _mutation_known(rehearsal, red, f"mutation red: {', '.join(outcome.tool for outcome in red)}", config, home, tools)
    unproven = [outcome for outcome in outcomes if outcome.proves_nothing()]
    if unproven:
        return _refused_as_unproven(rehearsal, unproven, pending, config, home, tools)
    rehearsal.mutated = pending["head"]
    return _mutation_known(rehearsal, [], _mutation_green_line(outcomes), config, home, tools)


def _mutation_known(rehearsal, red, line, config, home, tools):
    """Le résultat de la mutation rejoint le verdict du Critic : déjà là, ils décident ensemble ; sinon le résultat
    l'attend. Une Rehearsal escaladée garde le résultat pour sa reprise, et reste escaladée."""
    if rehearsal.status == "escalated" or not rehearsal.held_verdict:
        rehearsal.mutation_red = [asdict(outcome) for outcome in red]
    if rehearsal.status == "escalated":
        return Step("escalate", rehearsal.reason, [line])
    if not rehearsal.held_verdict:
        return Step("wait", done=[f"{line}: waiting for the Critic's verdict"])
    held, rehearsal.held_verdict = rehearsal.held_verdict, {}
    return _decide(rehearsal, held["verdict"], held["text"], red, Step("wait", done=[line]), config, home, tools)


def _refused_as_unproven(rehearsal, unproven, pending, config, home, tools):
    """Vert par son code de sortie mais sans preuve : une mutation partielle est relancée une fois sur toute la
    branche ; sinon (déjà sur toute la branche, ou relance qui ne prouve rien non plus), escalade."""
    for outcome in unproven:
        _log(home, rehearsal, "mutation-inconclusive", {"tool": outcome.tool, "log": outcome.log})
    whys = ", ".join(f"{outcome.tool}: {_unproven_reason(outcome)}" for outcome in unproven)
    if rehearsal.mutated and not pending.get("whole"):
        scoped = ballet_mutation.scopes_of(_mutation_tools(config), tools.git(rehearsal.worktree))
        line = f"mutation proved nothing on the last changes ({whys}): run again on the whole branch"
        return Step("wait", done=[line, _launch_mutation(rehearsal, scoped, home, tools, whole=True)])
    details = "; ".join(f"{outcome.tool} ({_unproven_reason(outcome)}), its log: {outcome.log}" for outcome in unproven)
    return Step("escalate", f"mutation proved nothing: {details}")


def _unproven_reason(outcome):
    """Pourquoi un outil vert ne prouve rien, en une expression."""
    if isinstance(outcome.report, dict):
        return f"no viable mutant ({outcome.report['invalid']} unviable)"
    return "report missing" if outcome.report == "missing" else outcome.report


def _mutation_green_line(outcomes):
    return "mutation green: " + ", ".join(f"{outcome.tool} ({_score_text(outcome.report)})" for outcome in outcomes)


def _score_text(report):
    if not isinstance(report, dict):
        return f"report {report}"
    return f"{report['killed']} killed, {report['survived']} survived" + (f", score {report['score']}" if report["score"] is not None else "")


def _mutation_tools(config):
    return ballet_mutation.tools_of(next(iter(config["repos"].values())))


def _conductor_run(rehearsal, tools):
    """Le Run Orca des workers de la Rehearsal, lu sur le dispatch du Dancer : c'est celui du Conductor."""
    shown = json.loads(tools.orca(["orchestration", "worker-show", "--dispatch", rehearsal.dispatches["dancer"], "--json"]))
    run_id = ballet_orca.find_key(shown, "runId")
    if not run_id:
        raise RehearsalError(f"the Dancer's dispatch {rehearsal.dispatches['dancer']} names no Orca Run: the mutation could not wake the Conductor")
    return run_id


def _mutation_results_path(rehearsal, home):
    folder = _run_dir(home) / rehearsal.id
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"mutation-{rehearsal.mutation['round']}.json"


def _is_mutation_wake(message):
    return message.get("type") == "status" and ballet_orca.payload(message).get("ballet") == "mutation"


def _verified_and_owned(rehearsal, role, config, home, tools):
    """Le Choreographer ou le Dramaturg, en pleine mission (il répond, ou il pose une question) : ses commits depuis le
    dernier passage sont vérifiés, et ne sont à lui que s'ils sont en règle."""
    found = _policy(rehearsal, role, config, home, tools, answering=True)
    if not found:
        _own_commits(rehearsal, tools)
    return found


def _own_commits(rehearsal, tools):
    """Les commits d'un passage vérifié du Choreographer ou du Dramaturg ne comptent pas contre le Dancer, ni contre
    le rôle qui reçoit ensuite la main : le point de contrôle avance avec eux."""
    git = tools.git(rehearsal.worktree)
    rehearsal.owned += ballet_policy.commits_since(rehearsal.checkpoint, git)
    rehearsal.checkpoint = ballet_policy.head(git)


def _then_premiere(rehearsal, step, config, tools):
    """La Premiere après ce qui est déjà fait : un merge refusé escalade sans perdre ces lignes."""
    try:
        premiere_step = _premiere(rehearsal, config, tools)
    except (RehearsalError, ballet_github.GitHubError) as error:
        return Step("escalate", f"merge refused: {error}", step.done)
    return Step(premiere_step.next, premiere_step.reason, step.done + premiere_step.done)


def _premiere(rehearsal, config, tools):
    """Merge par rebase (le script GitHub refuse sans `ballet:approved` frais ni CI verte), puis range le worktree."""
    if not rehearsal.pull_request:
        raise RehearsalError("no pull request to merge")
    waited = _merge_once_ci_settles(rehearsal, config["escalation"]["ci_wait_seconds"], tools)
    closed = _close_issues(rehearsal, tools)
    tools.orca(["worktree", "rm", "--worktree", f"path:{rehearsal.worktree}", "--delete-branch"])
    return Step("done", f"#{rehearsal.pull_request} merged on main",
                waited + [f"#{rehearsal.pull_request} merged by rebase, {rehearsal.branch} deleted", closed, "worktree removed"])


def _merge_once_ci_settles(rehearsal, wait_seconds, tools):
    """Une CI en cours se réattend, jusqu'à `ci_wait_seconds` ; une CI rouge, ou trop longue, refuse le merge."""
    waited = 0
    while True:
        try:
            ballet_github.merge_pull_request(rehearsal.pull_request, run=tools.gh, git=tools.git(rehearsal.repo))
            return [f"waited {waited}s for the CI"] if waited else []
        except ballet_github.CiPending as pending:
            if waited >= wait_seconds:
                raise RehearsalError(f"{pending} after waiting {waited}s (ci_wait_seconds)") from pending
            tools.sleep(CI_POLL_SECONDS)
            waited += CI_POLL_SECONDS


def _close_issues(rehearsal, tools):
    """Le merge est fait : une issue restée ouverte se signale, elle n'arrête pas la Premiere."""
    try:
        closed = ballet_github.close_issue(rehearsal.issue, rehearsal.pull_request, run=tools.gh)
    except (RehearsalError, ballet_github.GitHubError) as error:
        return f"issue #{rehearsal.issue} left open: {error}; close it by hand"
    return "issues closed: " + (", ".join(f"#{number}" for number in closed) or f"none, #{rehearsal.issue} was already closed")


# --- l'état en clair ----------------------------------------------------------


def _where(rehearsal):
    return f"Rehearsal {rehearsal.id}: {_target(rehearsal)}, branch {rehearsal.branch}, worktree {rehearsal.worktree or 'none'}"


def _pull_request_line(rehearsal, tools):
    if not rehearsal.pull_request:
        return "no pull request yet"
    try:
        found = ballet_github.pull_request_status(rehearsal.pull_request, run=tools.gh)
    except (RehearsalError, ballet_github.GitHubError) as error:
        return f"pull request #{rehearsal.pull_request}: cannot read it ({error})"
    state = f" ({found['state'].lower()})" if found["state"] else ""
    return (f"pull request #{rehearsal.pull_request}{state}: {found['label'] or 'no verdict label'}, "
            f"Critic's last verdict {found['verdict'] or 'none yet'}, {found['ci']}")


def _size_line(rehearsal):
    size = rehearsal.size
    if not size:
        return "diff not measured yet"
    verdict = "over the limit" + (", strict" if size["strict"] else ", not blocking") if size["over"] else "within the limit"
    return f"diff: {size['counted']} lines counted, {size['excluded']} excluded, limit {size['limit']}: {verdict}"


def _round_trips_line(rehearsal, config):
    return f"Dancer ↔ Critic round trips: {rehearsal.round_trips} of {config['escalation']['max_round_trips']}"


def _mutation_lines(rehearsal):
    if not rehearsal.mutation:
        return []
    held = f"; the Critic's verdict ({rehearsal.held_verdict['verdict']}) waits for it" if rehearsal.held_verdict else ""
    return [f"mutation running in the background since {rehearsal.mutation['started']} (round {rehearsal.mutation['round']}): "
            f"it wakes the Conductor when it is done{held}"]


def _pending_lines(rehearsal):
    return [f"the {question['from']} waits for the {question['to']}'s answer (Orca message {question['id']})"
            for question in rehearsal.pending]


def _workers_line(rehearsal):
    if not rehearsal.dispatches:
        return []
    return ["workers: " + ", ".join(f"{role} {dispatch}" for role, dispatch in rehearsal.dispatches.items())]


# --- les rôles ----------------------------------------------------------------


def _ask_role(rehearsal, role, assignment, config, home, tools):
    """Un rôle déjà lancé reçoit la suite dans sa session, avec son contexte ; sinon il démarre."""
    rehearsal.checkpoint = ballet_policy.head(tools.git(rehearsal.worktree))
    dispatch = rehearsal.dispatches.get(role)
    if dispatch:
        tools.orca(["orchestration", "send", "--to", f"dispatch:{dispatch}",
                    "--subject", f"{rehearsal.id} · {role}", "--body", assignment])
        _log_handoff(rehearsal, role, "send", assignment, home)
    else:
        _start_worker(rehearsal, role, assignment, config, home, tools)


def _start_worker(rehearsal, role, assignment, config, home, tools):
    if role == "dancer" and not rehearsal.dancer_start:
        rehearsal.dancer_start = rehearsal.checkpoint     # `HEAD` du worktree : il vient d'être relevé par l'appelant
    route = config["roles"][role]
    agent = ORCA_AGENTS.get(route.get("cli"))
    if not agent:
        raise RehearsalError(f"the {role}'s CLI `{route.get('cli')}` cannot run as an Orca worker yet")
    spec = _write_spec(rehearsal, role, _role_spec(rehearsal, role, assignment), home)
    dispatch = ballet_orca.start_worker(spec, rehearsal.worktree, agent, f"{role.capitalize()} · {rehearsal.id}", tools,
                                        model=route.get("model", ""))
    if not dispatch:
        raise RehearsalError("the worker started but its receipt names no dispatchId")
    rehearsal.dispatches[role] = dispatch
    _log_handoff(rehearsal, role, "start", assignment, home, {"agent": agent, "model": route.get("model", "")})


def _log_handoff(rehearsal, role, how, text, home, extra=None):
    """Ce que le Conductor remet à un worker : `start` (lancé), `send` (relancé dans sa session), `reply` (la réponse
    à sa question) ou `nudge` (rappel de son `worker_done`), avec le texte entier."""
    detail = {"role": role, "dispatch": rehearsal.dispatches.get(role, ""), "how": how, **(extra or {}), "text": text}
    _log(home, rehearsal, "handoff", detail)


def _role_spec(rehearsal, role, assignment):
    pull_request = f", pull request #{rehearsal.pull_request}" if rehearsal.pull_request else ""
    return f"""You are the Ballet {role.capitalize()} of Rehearsal {rehearsal.id}: {_target(rehearsal)}{pull_request}, branch `{rehearsal.branch}`, in this worktree.

Load the skill `/ballet:{role}` and follow it. Its GitHub script is {SKILLS_ROOT.parent / "scripts" / "ballet_github.py"}.

{assignment}

Under the Conductor:
- A question: one Ballet message (`templates/message.md`, `type: question`), sent with `orca orchestration ask --question "<the whole message>"`. Then end your turn: the answer comes back here, in this session.
- When you are done: send your `worker_done`, whose body is your final message, whole, header line first. Ending your turn without sending it stops the Rehearsal.
- Never push, never run `gh`, never change branch (spikes excepted, for the Choreographer).
"""


def _first_assignment(role, rehearsal, config):
    if role == "dancer":
        return f"Execute your repo's section of the plan of issue #{rehearsal.issue}, task by task."
    if rehearsal.feature:
        publish = (f"Plan the ready feature {rehearsal.feature}, which has no issue yet: publish it (`publish <file> Feature in-rehearsal`), "
                   "then its plan, and its slices (`slice`) if it needs them.")
    else:
        publish = (f"Issue #{rehearsal.issue} has no plan yet: write it (`plan {rehearsal.issue}`), or cut it into slices "
                   f"(`slice {rehearsal.issue}`).")
    return f"{publish}\n\n{_auto_mode(rehearsal, config)}"


def _auto_mode(rehearsal, config):
    """La consigne du Choreographer en mode auto : il tranche seul, découpe en slices verticales sous le seuil et publie sans attendre de oui."""
    limit = config["escalation"]["max_diff_lines"]
    review = ("the Director reviews the published plan before any code, and may then ask you questions or changes "
              "through the Conductor" if rehearsal.plan == "review" else "the Dancer starts on it as soon as you report")
    return (f"Auto mode (section *Auto mode* of your skill): nobody says yes in this session; {review}. Settle every "
            "choice yourself and write it in *Decisions*. Product gaps go to the Dramaturg; what neither of you can settle "
            f"goes to the Director (a question `to: director`). Slices: one plan when it can; otherwise at most "
            f"{MAX_SLICES} slices, cut by criterion: each one delivers one or more whole criteria end to end, never one "
            f"layer (API, then client, then screen). `max_diff_lines` ({limit}) only marks a pull request too big to "
            "review: it does not cut slices. "
            "Commit your ADRs and `AGENTS.md` rules on this branch: they ship with the first slice. "
            "Then report, with `- Issue: #<n>` (the parent, when sliced).")


def _review_round(rehearsal):
    """Le numéro du prochain tour de review : un refus, ou une approbation que la mutation rouge renvoie, en ouvrent un."""
    return max(rehearsal.reviews, rehearsal.round_trips) + 1


def _critic_assignment(rehearsal, config):
    return (f"Review pull request #{rehearsal.pull_request} of issue #{rehearsal.issue}, round {_review_round(rehearsal)}: "
            f"the branch `{rehearsal.branch}` against the plan. Ballet already ran the proof (`{_proof_command(config)}`) "
            f"on {rehearsal.proven[:7] or 'HEAD'}, green; the mutation test, when the profile has one, runs alongside your "
            "review and Ballet weighs it with your verdict: run neither.")


def _red_fix_assignment(without_red):
    listed = "\n".join(f"- {task}" for task in without_red)
    return ("Ballet refused your report: nothing was pushed nor run. These done tasks have no `Red:` line:\n\n"
            f"{listed}\n\nEach done task quotes its red on the line under it: `- Red: <test name>: <the failure line, "
            "as the runner printed it, before the code>`. A task with no behaviour to test (a chore) says `- Red: none — <why>`. "
            "Then report again, whole. Change no code for this.")


def _director_fix_assignment(rehearsal, comments, red, config):
    quoted = "\n\n".join(_quote(comment) for comment in comments)
    mutation = f"\n\n{_mutation_part(red, config)}" if red else ""
    return (f"The Director rejected pull request #{rehearsal.pull_request}. Their comments, your blocking points:\n\n{quoted}"
            f"{mutation}\n\nFix each one, then report again (`read-pr {rehearsal.pull_request}` for the whole pull request).")


def _policy_fix_assignment(found):
    listed = "\n".join(f"- {violation}" for violation in found)
    return (f"Ballet's policy refused your work: nothing was pushed.\n\n{listed}\n\nFix it with new commits "
            "(a revert is fine), never by rewriting history, and leave the worktree clean. If the plan really needs "
            "one of these changes, ask instead. Then report again. A second violation goes to the Director.")


def _proof_fix_assignment(command, proof):
    tail = "\n".join(proof.output.rstrip().splitlines()[-PROOF_OUTPUT_LINES:])
    return (f"Ballet ran the proof (`{command}`) on your branch: it is red. Nothing was pushed, and the Critic was not "
            f"asked. The end of its output:\n\n```\n{tail}\n```\n\nMake it green with new commits, never by touching "
            "an existing test, and leave the worktree clean. Then report again.")


def _mutation_part(red, config):
    """Les survivants des outils rouges, et comment les traiter : une partie de la mission du Dancer."""
    sections = "\n\n".join(_mutation_section(outcome, config) for outcome in red)
    return ("Ballet's mutation test on the same commit is red.\n\n"
            f"{sections}\n\nKill each survivor with a unit test, never an end-to-end test (skill `ballet:tdd`). A survivor "
            "that is truly equivalent (no test can tell it apart) is excluded in the tool's config file, with its reason "
            "written next to it: the Critic judges each exclusion.")


def _mutation_section(outcome, config):
    """Un outil rouge : ses survivants (sinon la fin de sa sortie), son log entier et le fichier de ses équivalents."""
    tool = next(tool for tool in _mutation_tools(config) if tool.name == outcome.tool)
    listed = "Survivors" if outcome.lists_survivors() else f"No survivor list (report: {outcome.report_status()}); the end of its output"
    return (f"### {outcome.tool} (exit {outcome.exit_code})\n\n{listed}:\n\n```\n{outcome.survivors_text()}\n```\n\n"
            f"Whole log: `{outcome.log}`. Equivalents go in `{tool.config}`.")


def _quote(text):
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def _fix_assignment(rehearsal, verdict, red, config):
    """Un seul tour du Dancer : les points du Critic qui rejette, les survivants de la mutation, ou les deux."""
    if verdict == "APPROVED":
        critic = (f"The Critic approved pull request #{rehearsal.pull_request}, but the mutation decides too: the Critic "
                  "reviews again after your fix. Its notes are not yours to take now.")
    else:
        critic = (f"Round {_review_round(rehearsal)}: the Critic rejected pull request #{rehearsal.pull_request}. Read its "
                  f"review (`read-pr {rehearsal.pull_request}`), fix each blocking point, then take its notes in one last commit.")
    mutation = f"\n\n{_mutation_part(red, config)}" if red else ""
    return f"{critic}{mutation}\n\nNew commits only, the worktree clean. Then report again."


# --- état, journal et publication ---------------------------------------------


def _count_round(rehearsal, header, config):
    """Compte les tours par sujet et par paire de rôles ; au-delà du plafond, le Director tranche."""
    if header["type"] not in ("question", "answer"):
        return
    pair = sorted([header["from"], header["to"]])
    key = f"{header['subject']}|{pair[0]}>{pair[1]}"
    rehearsal.rounds[key] = max(rehearsal.rounds.get(key, 0), header["round"])
    limit = config["escalation"]["max_exchange_rounds"]
    if header["round"] > limit:
        raise RehearsalError(f"round {header['round']} on {header['subject']} between {pair[0]} and {pair[1]}, over max_exchange_rounds ({limit})")


def _pending_question(rehearsal, asker, answerer):
    for question in rehearsal.pending:
        if question["from"] == asker and question["to"] == answerer:
            return question
    raise RehearsalError(f"no pending question from the {asker} to the {answerer}")


def _publish_exchange(rehearsal, what, text, home, tools):
    """Une question ou une réponse va sur l'issue ; une planification n'en a pas encore : le journal la garde seul."""
    if not rehearsal.issue:
        return f"{what} not published: no issue yet, the journal keeps it"
    _comment_issue(rehearsal, text, home, tools)
    return f"{what} published on issue #{rehearsal.issue}"


def _comment_issue(rehearsal, text, home, tools):
    ballet_github.comment_issue(rehearsal.issue, _outbox(text, home), run=tools.gh)


def _comment_pull_request(rehearsal, text, home, tools):
    ballet_github.comment_pull_request(rehearsal.pull_request, _outbox(text, home), run=tools.gh)


def _publish_review(rehearsal, text, home, tools):
    ballet_github.publish_review(rehearsal.pull_request, _outbox(text, home), run=tools.gh)


def _resolve_fixed_points(rehearsal, report, home, tools):
    resolved, unmatched = ballet_github.resolve_fixed(rehearsal.pull_request, _outbox(report, home), run=tools.gh)
    summary = f"threads resolved: {', '.join(resolved) or 'none'}"
    return summary + (f"; no open thread for: {', '.join(unmatched)}" if unmatched else "")


def _outbox(text, home):
    """Le script GitHub publie depuis un fichier : le message passe par `outbox.md`, dans le dossier de travail du projet."""
    outbox = _run_dir(home) / "outbox.md"
    outbox.write_text(text, encoding="utf-8")
    return outbox


def _write_spec(rehearsal, role, spec, home):
    folder = _run_dir(home) / rehearsal.id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{role}-{len(list(folder.glob(f'{role}-*.md'))) + 1}.md"
    path.write_text(spec, encoding="utf-8")
    return path


def _label(rehearsal, verdict, tools):
    ballet_github.label_pull_request(rehearsal.pull_request, verdict, run=tools.gh)
    rehearsal.label = verdict


def _flag_escalation(rehearsal, step, tools):
    """Une escalade avec une PR pose `ballet:escalated`, sauf sur une approbation en vigueur (CI en cours)
    ou une escalade déjà posée : le libellé qu'y met ensuite le Director reste le sien."""
    if step.next != "escalate" or not rehearsal.pull_request or rehearsal.label in ("APPROVED", "ESCALATE"):
        return
    try:
        _label(rehearsal, "ESCALATE", tools)
        step.done.append(f"#{rehearsal.pull_request} labelled ballet:escalated: the Director decides")
    except (RehearsalError, ballet_github.GitHubError) as error:
        step.done.append(f"#{rehearsal.pull_request} not labelled ballet:escalated: {error}")


def _settle(rehearsal, step, home, tools):
    """Le pas fixe le statut de la Rehearsal (et le libellé d'une escalade) ; l'état est sauvé et le pas journalisé.
    Une Premiere passe la main à l'élément suivant de la session ; le Ballet status de son issue suit."""
    _flag_escalation(rehearsal, step, tools)
    rehearsal.status = STATUS_OF_STEP[step.next]
    rehearsal.reason = step.reason
    _save(rehearsal, home)
    _log(home, rehearsal, step.next, {"reason": step.reason, "done": step.done})
    if step.next == "done":
        _record_frictions(rehearsal, home)
        step = _after_premiere(rehearsal, step, home, tools)
    return _follow_on_github(rehearsal.session, step, home, tools)


def _save(rehearsal, home):
    ballet_store.save(home, ballet_store.REHEARSAL, asdict(rehearsal))


def load(rehearsal_id, home):
    saved = ballet_store.load(home, ballet_store.REHEARSAL, rehearsal_id)
    if saved is None:
        raise RehearsalError(f"no Rehearsal {rehearsal_id} in project {ballet_store.project_of(home)}")
    return Rehearsal(**saved)


def _exists(rehearsal_id, home):
    return ballet_store.load(home, ballet_store.REHEARSAL, rehearsal_id) is not None


def _refuse_if_already_open(rehearsal, home):
    saved = ballet_store.load(home, ballet_store.REHEARSAL, rehearsal.id)
    if saved and saved["status"] != "done":
        raise RehearsalError(f"Rehearsal {rehearsal.id} is already open")


def _load_session(session_item, home):
    saved = ballet_store.load(home, "session", session_item)
    if saved is None:
        raise RehearsalError(f"no session of {session_item} in project {ballet_store.project_of(home)}")
    return Session(**saved)


def _save_session(session, home):
    ballet_store.save(home, "session", asdict(session))


def _session_exists(session_item, home):
    return ballet_store.load(home, "session", session_item) is not None


def _session_of(rehearsal, home):
    """La session de la Rehearsal ; aucune pour une Rehearsal d'avant les sessions."""
    if not rehearsal.session or not _session_exists(rehearsal.session, home):
        return None
    return _load_session(rehearsal.session, home)


def open_sessions(home):
    return [session for session in map(lambda saved: Session(**saved), ballet_store.all_of(home, "session")) if session.status == "open"]


def _log(home, rehearsal, event, detail):
    ballet_store.log(home, ballet_store.REHEARSAL, rehearsal.id, event, detail, conductor=rehearsal.session)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run_dir(home):
    """Le dossier de travail du projet, hors du projet : `~/.ballet/projects/<alias>/`."""
    return ballet_store.work_dir(home)


def inbox_path(home):
    """Où le Conductor écrit un message du Director avant de le recevoir (`receive <chemin>`)."""
    return _run_dir(home) / INBOX


# --- lectures -----------------------------------------------------------------


def _checked_config(home):
    try:
        config = ballet_config.effective_config(home)
    except ballet_config.ConfigError as error:
        raise RehearsalError(str(error)) from error
    problems = ballet_config.find_problems(config)
    if problems:
        raise RehearsalError("the profile is not valid, run /ballet:init-project: " + "; ".join(problems))
    return config


def _single_repo(config, home):
    repos = config.get("repos", {})
    if len(repos) != 1:
        raise RehearsalError("the Conductor v0 runs a single repo; this profile declares " + str(len(repos)))
    return (Path(home) / next(iter(repos.values()))["path"]).resolve()


def _rehearsal_of(item, config, home, tools):
    """La Rehearsal d'un élément et son premier rôle."""
    repo = str(_single_repo(config, home))
    if FEATURE_ITEM.match(item):
        return Rehearsal(id=item, issue="", repo=repo, feature=item), "choreographer"
    title, body = _issue(item, tools)
    rehearsal = Rehearsal(id=_rehearsal_id(title), issue=ballet_github._issue_number(item), repo=repo)
    return rehearsal, "dancer" if _has_tasks(body) else "choreographer"


def _item_of(rehearsal):
    return rehearsal.feature or f"#{rehearsal.issue}"


def _target(rehearsal):
    return f"issue #{rehearsal.issue}" if rehearsal.issue else f"feature {rehearsal.feature}, no issue yet"


def _report_field(report, name):
    match = re.search(rf"^- {name}:\s*(.+?)\s*$", report, re.MULTILINE)
    return match.group(1) if match else ""


def _report_issue(report):
    match = re.match(r"#?(\d+)\b", _report_field(report, "Issue"))
    return match.group(1) if match else ""


def _issue(issue, tools):
    output = tools.gh(["issue", "view", ballet_github._issue_number(issue), "--json", "title,body"])
    issue_data = json.loads(output)
    return issue_data["title"], issue_data["body"]


def _rehearsal_id(title):
    match = REHEARSAL_ID.match(title)
    if not match:
        raise RehearsalError(f"the issue title does not start with FEAT-NNN, FEAT-NNN.K, BUG-NNN or TASK-NNN: {title}")
    return match.group(1)


def _has_tasks(body):
    """Le plan a des tâches : des cases à cocher dans sa section `## Plan`."""
    text = f"\n{body}"
    plan = text.split("\n## Plan\n", 1)[1] if "\n## Plan\n" in text else ""
    return bool(re.search(r"^- \[[ x]\] ", plan, re.MULTILINE))


def _message(path):
    try:
        return read_message(path)
    except MessageError as error:
        raise RehearsalError(f"invalid message, send it back to its author: {error}") from error


def _parsed(body):
    try:
        return parse_message(body)
    except MessageError as error:
        raise RehearsalError(f"invalid message, send it back to its author: {error}") from error


def _orca_message(wanted, by, tools):
    """Le message entier, retrouvé dans la boîte d'Orca par son id ou comme le dernier du dispatch d'un worker.
    Un `escalation` d'Orca (worker arrêté sans rapport) n'est pas un message Ballet : `_worker_stopped` en décide."""
    message = ballet_orca.inbox_message(wanted, by, tools)
    if not message:
        raise RehearsalError(f"no Orca message {'from dispatch ' if by == 'dispatch' else ''}{wanted} in the inbox")
    return message


def _step_of_message(rehearsal, message, config, home, tools):
    """Un message lu chez Orca, noté comme reçu avant d'être traité : même en escalade, il n'est jamais rejoué."""
    if message.get("id") and message["id"] not in rehearsal.received:
        rehearsal.received.append(message["id"])
    if _is_mutation_wake(message):
        return _kept_escalation(rehearsal, _after_mutation(rehearsal, ballet_orca.payload(message).get("round"), config, home, tools))
    _follow_worker(rehearsal, message, home)
    if message.get("type") == "escalation":
        return _worker_stopped(rehearsal, message, home, tools)
    header, text = _parsed(message.get("body", ""))
    question_id = message["id"] if message.get("type") == "question" else None
    return _handle(rehearsal, header, text, question_id, config, home, tools)


def _received_step(rehearsal, message, config, home, tools):
    try:
        return _step_of_message(rehearsal, message, config, home, tools)
    except (RehearsalError, ballet_github.GitHubError) as error:
        return Step("escalate", str(error))


def _is_new_for(rehearsal, message):
    """Un message du Run qui revient à cette Rehearsal : d'un de ses workers, ou le réveil de sa mutation ; et pas encore traité."""
    if message.get("id") in rehearsal.received:
        return False
    if _is_mutation_wake(message):
        return ballet_orca.payload(message).get("rehearsal") == rehearsal.id
    return bool(_worker_role(rehearsal, message))


def _worker_role(rehearsal, message):
    return ballet_orca.worker_role(message, rehearsal.dispatches, rehearsal.handles)


def _follow_worker(rehearsal, message, home):
    """Le worker reconnu garde son handle, et son dernier dispatch : Orca le rouvre sous un nouveau à chaque envoi (journal
    `dispatch-moved`). C'est ce dispatch que `worker-show`, `stop` et le rappel visent ensuite."""
    role = _worker_role(rehearsal, message)
    if not role:
        return
    handle, dispatch = ballet_orca.worker_handle(message), ballet_orca.worker_dispatch(message)
    if handle and not rehearsal.handles.get(role):
        rehearsal.handles[role] = handle
    if dispatch and dispatch != rehearsal.dispatches.get(role):
        _log(home, rehearsal, "dispatch-moved", {"role": role, "from": rehearsal.dispatches.get(role, ""), "to": dispatch})
        rehearsal.dispatches[role] = dispatch


def _nothing_new(rehearsal, run_id, ignored):
    """Rien pour la Rehearsal dans le Run : son état ne bouge pas, et le pas le redit."""
    return Step(STEP_OF_STATUS[rehearsal.status], rehearsal.reason,
                [f"no new message for {rehearsal.id} in Orca run {run_id}" + (f" ({ignored} ignored)" if ignored else "")])


def _merged_steps(rehearsal, steps, left, ignored):
    """Les pas des messages traités en un seul : leurs lignes, puis ce qui reste à recevoir ; le `NEXT` du dernier."""
    last = steps[-1]
    done = [line for step in steps for line in step.done]
    done += [f"not processed after this step, still to receive: receive {rehearsal.id} --message {message['id']}" for message in left]
    done += [f"{ignored} message(s) of the run ignored: not for {rehearsal.id}, or already received"] if ignored else []
    return Step(last.next, last.reason, done, item=last.item)


def _open_worktree(rehearsal, tools):
    path = ballet_orca.open_worktree(rehearsal.repo, rehearsal.branch, tools, rehearsal.issue)
    if not path:
        raise RehearsalError(f"no worktree found for {rehearsal.branch} after its creation")
    return path


def _run_proof(command, cwd, timeout):
    """La preuve du profil, une ligne de shell ; trop longue, son groupe de processus est tué."""
    process = subprocess.Popen(command, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, errors="replace", start_new_session=True)
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        output, _ = process.communicate()
        return Proof(False, output, timed_out=True)
    return Proof(process.returncode == 0, output)


def _launch_detached(argv, cwd, work_dir):
    """Un processus qui survit à l'appel du Conductor, son environnement compris (Orca y reconnaît le Conductor)."""
    with open(Path(work_dir) / "mutation-launch.log", "a", encoding="utf-8") as log:
        subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)


def _run(arguments):
    completed = subprocess.run(arguments, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RehearsalError(completed.stderr.strip() or completed.stdout.strip() or f"{arguments[0]} failed")
    return completed.stdout


# --- ligne de commande --------------------------------------------------------


def main(argv, home=".", tools=None):
    """Affiche le pas et sort avec 0, escalade comprise ; 2 sur un usage invalide."""
    tools = tools or Tools()
    command, arguments = (argv[1], argv[2:]) if len(argv) > 1 else (None, [])
    try:
        ballet_legacy.refuse_if_pending(homes=[home])
        print(_shown(_command(command, arguments, home, tools), home, tools))
    except UsageError as error:
        print(error, file=sys.stderr)
        return 2
    except (RehearsalError, ballet_github.GitHubError, ballet_legacy.LegacyError) as error:
        print(_shown(Step("escalate", str(error), item=named_item(command, arguments)), home, tools))
    return 0


def named_item(command, arguments):
    """L'élément nommé sur la ligne de commande (`#12`, `FEAT-002`), sinon `?` : une panne est annoncée à Maestro
    même avant que la session existe. Rien pour `status`, une simple lecture."""
    if command == "status":
        return ""
    return next((item for item in map(_as_item, arguments) if item), "?")


def _shown(result, home, tools):
    """Le texte à afficher ; une escalade ou la fin d'une session est d'abord annoncée à Maestro."""
    if not isinstance(result, Step):
        return result
    ballet_maestro.announce(result, home, tools.orca)
    if result.next == "escalate":
        result.done.append(f"a message from the Director goes to {inbox_path(home)}, then receive it")
    return result.render()


USAGE = ("usage: begin <item> | receive [<ID>] --run <run-id> | receive [<ID>] --message <msg-id> | receive [<ID>] --dispatch <ctx-id> "
         "| receive [<ID>] <message.md> [--question <msg-id>] | receive [<ID>] --mutation | premiere [<ID>] "
         "| resume [<ID> | <item>] | status [<ID> | <item>] | status <ID> --json | nudge [<ID>]   (an item: #<issue> (a Feature, a Bug or a Task) "
         "or a ready FEAT-NNN; no <ID>: the Rehearsal of the only open session)")


OPTIONS = ("--run", "--message", "--dispatch", "--question", "--mutation", "--json")


def _command(command, arguments, home, tools):
    _refuse_help_and_unknown_options(command, arguments)
    if command == "begin" and len(arguments) == 1:
        return begin(_item(arguments[0]), home, tools)
    if command in ("resume", "status") and len(arguments) <= 1:
        session_item = _session_named(arguments[0], home) if arguments else _only_open_session(home)
        if session_item or not arguments:
            return _session_command(command, session_item, home, tools)
    if command in ("receive", "premiere", "resume", "status", "nudge") and not _names_a_rehearsal(arguments):
        arguments = [_current_rehearsal(home), *arguments]
    return _rehearsal_command(command, arguments, home, tools)


def _session_command(command, session_item, home, tools):
    if not session_item:
        return Step("done", "no session is open")
    if command == "resume":
        return resume_session(session_item, home, tools)
    return status_session(session_item, home, tools)


def _rehearsal_command(command, arguments, home, tools):
    if command == "receive" and arguments[1:] == ["--mutation"]:
        return receive_mutation(arguments[0], home, tools)
    if command == "mutate" and len(arguments) == 1:
        mutate(arguments[0], home, tools)
        return f"mutation of {arguments[0]} done"
    if command == "receive" and len(arguments) == 3 and arguments[1] == "--run":
        return receive_from_run(arguments[0], arguments[2], home, tools)
    if command == "receive" and len(arguments) == 3 and arguments[1] in ("--message", "--dispatch"):
        return receive_from_orca(arguments[0], arguments[2], home, tools, by=arguments[1][2:])
    if command == "receive" and len(arguments) in (2, 4) and arguments[2:3] in ([], ["--question"]):
        return receive(arguments[0], arguments[1], arguments[3] if len(arguments) == 4 else None, home, tools)
    if command == "nudge" and len(arguments) == 1:
        return nudge(arguments[0], home, tools)
    if command == "premiere" and len(arguments) == 1:
        return premiere(arguments[0], home, tools)
    if command == "resume" and len(arguments) == 1:
        return resume(arguments[0], home, tools)
    if command == "status" and len(arguments) == 1:
        return status(arguments[0], home, tools)
    if command == "status" and arguments[1:] == ["--json"]:
        return json.dumps(asdict(load(arguments[0], home)), indent=2)
    raise UsageError(USAGE)


def _refuse_help_and_unknown_options(command, arguments):
    """`--help`, `-h` ou une option inconnue : l'usage, rien d'autre (ni état touché, ni Orca, ni Maestro)."""
    options = [argument for argument in arguments if argument.startswith("-")]
    if command in ("-h", "--help") or any(option not in OPTIONS for option in options):
        raise UsageError(USAGE)


def _item(text):
    """Un élément confié : une issue (`#12`, `12`) ou une feature prête (`FEAT-002`)."""
    item = _as_item(text)
    if not item:
        raise UsageError(f"not an item: {text}\n" + USAGE)
    return item


def _as_item(text):
    if FEATURE_ITEM.match(text):
        return text
    match = ISSUE_ITEM.match(text)
    return f"#{match.group(1)}" if match else None


def _names_a_rehearsal(arguments):
    return bool(arguments) and bool(REHEARSAL_ID.fullmatch(arguments[0]))


def _session_named(text, home):
    """L'élément d'une session qui existe (`#12`, `FEAT-002`) ; une session passe avant la Rehearsal du même nom."""
    item = _as_item(text)
    return item if item and _session_exists(item, home) else None


def _only_open_session(home):
    """Sans `<ID>` : la seule session ouverte ; plusieurs, il faut la nommer."""
    sessions = open_sessions(home)
    if len(sessions) > 1:
        listed = ", ".join(f"{session.item} playing {session.current or 'nothing'}" for session in sessions)
        raise UsageError(f"{len(sessions)} sessions are open ({listed}): name the Rehearsal <ID> or the session's item\n" + USAGE)
    return sessions[0].item if sessions else None


def _current_rehearsal(home):
    session_item = _only_open_session(home)
    current = _load_session(session_item, home).current if session_item else ""
    if not current:
        raise UsageError("no Rehearsal is playing: name its <ID>\n" + USAGE)
    return current


if __name__ == "__main__":
    sys.exit(main(sys.argv))
