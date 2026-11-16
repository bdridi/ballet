"""Le Conductor déterministe : l'état d'une Rehearsal, ses transitions, et chaque action qu'elles déclenchent.

    python3 ballet_rehearsal.py begin    <issue>                                   # ouvre la Rehearsal, lance le premier rôle
    python3 ballet_rehearsal.py receive  <ID> <message.md> [--question <msg-id>]   # un message d'un worker, ou du Director
    python3 ballet_rehearsal.py premiere <ID>                                      # retente le merge (CI encore en cours)
    python3 ballet_rehearsal.py status   <ID> [--json]                             # où en est la Rehearsal

Lancé depuis le home du projet. Le skill `conductor` n'a qu'à appeler ce script et lire sa dernière ligne :
    NEXT: wait               un worker travaille ; Orca réveillera le Conductor
    NEXT: escalate <motif>   le Director décide ; la Rehearsal attend
    NEXT: done               la Premiere est faite

Une escalade est un cas prévu : le script sort avec 0. Il sort avec 2 sur un usage invalide,
et un autre code ≠ 0 n'est qu'une panne du script.

L'état vit dans `.ballet/run/<ID>.json`, le journal dans `.ballet/run/journal.jsonl`
(`init-project` met `.ballet/run/` dans le `.gitignore` du projet).
"""

import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import ballet_config
import ballet_github
from ballet_message import MessageError, read_message, verdict_of

RUN_DIR = Path(".ballet") / "run"
REHEARSAL_ID = re.compile(r"^((?:FEAT|BUG|TASK)-\d{3}(?:\.\d+)?)\b")
ORCA_AGENTS = {"claude": "claude", "codex": "codex", "grok": "grok", "opencode": "opencode"}
SKILLS_ROOT = Path(__file__).resolve().parent.parent / "skills"
STATUS_OF_STEP = {"wait": "open", "escalate": "escalated", "done": "done"}
STEP_OF_STATUS = {status: step for step, status in STATUS_OF_STEP.items()}


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
    rounds: dict = field(default_factory=dict)       # "sujet|de>à" → dernier round vu
    dispatches: dict = field(default_factory=dict)   # rôle → dispatch Orca de son worker
    pending: list = field(default_factory=list)      # questions en attente : {id, from, to}
    status: str = "open"                             # open | escalated | done
    reason: str = ""                                 # le motif de la dernière escalade, ou de la fin

    @property
    def branch(self):
        return f"rehearsal/{self.id}"


@dataclass
class Step:
    """Ce que le Conductor fait ensuite : `wait`, `escalate` ou `done`, avec ce qui s'est passé."""
    next: str
    reason: str = ""
    done: list = field(default_factory=list)

    def render(self):
        lines = [f"- {action}" for action in self.done]
        return "\n".join(lines + [f"NEXT: {self.next} {self.reason}".rstrip()])


class Tools:
    """Les commandes externes (git, gh, orca), remplaçables dans les tests."""

    def __init__(self, run=None):
        self.run = run or _run

    def gh(self, arguments):
        return self.run(["gh", *arguments])

    def git(self, repo):
        return lambda arguments: self.run(["git", "-C", repo, *arguments])

    def orca(self, arguments):
        return self.run([os.environ.get("ORCA_CLI_COMMAND", "orca"), *arguments])


# --- les trois entrées du Conductor -------------------------------------------


def begin(issue, home, tools):
    config = _checked_config(home)
    repo = _single_repo(config, home)
    title, body = _issue(issue, tools)
    rehearsal = Rehearsal(id=_rehearsal_id(title), issue=ballet_github._issue_number(issue), repo=str(repo))
    _refuse_if_already_open(rehearsal, home)
    step = Step("wait")
    rehearsal.worktree = _open_worktree(rehearsal, tools)
    step.done.append(f"worktree {rehearsal.worktree} on {rehearsal.branch}, from origin/main")
    first_role = "dancer" if _has_tasks(body) else "choreographer"
    _start_worker(rehearsal, first_role, _first_assignment(first_role, rehearsal), config, home, tools)
    step.done.append(f"{first_role} started on issue #{rehearsal.issue}")
    _log(home, rehearsal, "begin", {"first_role": first_role})
    return _settle(rehearsal, step, home)


def receive(rehearsal_id, message_path, question_id, home, tools):
    config = _checked_config(home)
    rehearsal = _load(rehearsal_id, home)
    try:
        header, text = _message(message_path)
        _log(home, rehearsal, "message", header)
        step = _route(rehearsal, header, text, question_id, config, home, tools)
    except (RehearsalError, ballet_github.GitHubError) as error:
        step = Step("escalate", str(error))
    return _settle(rehearsal, step, home)


def premiere(rehearsal_id, home, tools):
    rehearsal = _load(rehearsal_id, home)
    try:
        step = _premiere(rehearsal, tools)
    except (RehearsalError, ballet_github.GitHubError) as error:
        step = Step("escalate", f"merge refused: {error}")
    return _settle(rehearsal, step, home)


def status(rehearsal_id, home, tools):
    """Où en est la Rehearsal, en clair : sa dernière ligne `NEXT` est celle du dernier pas."""
    config = _checked_config(home)
    rehearsal = _load(rehearsal_id, home)
    summary = [_where(rehearsal), _pull_request_line(rehearsal, tools), _round_trips_line(rehearsal, config)]
    summary += _pending_lines(rehearsal) + _workers_line(rehearsal)
    return Step(STEP_OF_STATUS[rehearsal.status], rehearsal.reason, summary)


# --- les transitions ----------------------------------------------------------


def _route(rehearsal, header, text, question_id, config, home, tools):
    _count_round(rehearsal, header, config)
    kind, sender = header["type"], header["from"]
    if kind == "question":
        return _relay_question(rehearsal, header, text, question_id, config, home, tools)
    if kind == "answer":
        return _relay_answer(rehearsal, header, text, home, tools)
    if kind == "report" and sender == "choreographer":
        return _after_plan(rehearsal, config, home, tools)
    if kind == "report" and sender == "dancer":
        return _after_code(rehearsal, text, config, home, tools)
    if kind == "verdict" and sender == "critic":
        return _after_verdict(rehearsal, verdict_of(text), text, config, home, tools)
    if kind == "escalation":
        return Step("escalate", f"{sender} escalates: see its message")
    raise RehearsalError(f"no transition for a {kind} from the {sender}")


def _relay_question(rehearsal, header, text, question_id, config, home, tools):
    """Publie la question sur l'issue, puis la porte au rôle qui doit répondre ; le demandeur attend, éveillé."""
    if not question_id:
        raise RehearsalError("a question needs the Orca message id (--question) to send the answer back")
    step = Step("wait")
    _comment_issue(rehearsal, text, home, tools)
    step.done.append(f"question published on issue #{rehearsal.issue}")
    rehearsal.pending.append({"id": question_id, "from": header["from"], "to": header["to"]})
    if header["to"] == "director":
        return Step("escalate", f"the {header['from']} asks the Director: answer with an `answer` message", step.done)
    _ask_role(rehearsal, header["to"], f"Answer this question from the {header['from']}, then return your answer "
              f"as a Ballet message (`type: answer`, to the {header['from']}):\n\n{text}", config, home, tools)
    step.done.append(f"question carried to the {header['to']}")
    return step


def _relay_answer(rehearsal, header, text, home, tools):
    """Publie la réponse sur l'issue et la rend au demandeur, qui reprend avec son contexte."""
    question = _pending_question(rehearsal, asker=header["to"], answerer=header["from"])
    step = Step("wait")
    _comment_issue(rehearsal, text, home, tools)
    step.done.append(f"answer published on issue #{rehearsal.issue}")
    tools.orca(["orchestration", "reply", "--id", question["id"], "--body", text])
    rehearsal.pending.remove(question)
    step.done.append(f"answer handed back to the {header['to']}")
    return step


def _after_plan(rehearsal, config, home, tools):
    _, body = _issue(rehearsal.issue, tools)
    if not _has_tasks(body):
        raise RehearsalError(f"the Choreographer reported but issue #{rehearsal.issue} has no tasks (slices?)")
    _ask_role(rehearsal, "dancer", _first_assignment("dancer", rehearsal), config, home, tools)
    return Step("wait", done=[f"plan found on issue #{rehearsal.issue}", "dancer started"])


def _after_code(rehearsal, report, config, home, tools):
    """Pousse la branche, ouvre la PR au premier rapport, y publie le rapport, puis passe la main au Critic."""
    step = Step("wait")
    ballet_github.push_branch(rehearsal.branch, git=tools.git(rehearsal.repo))
    step.done.append(f"{rehearsal.branch} pushed")
    if rehearsal.pull_request:
        step.done.append(_resolve_fixed_points(rehearsal, report, home, tools))
    else:
        rehearsal.pull_request = ballet_github.open_pull_request(rehearsal.issue, rehearsal.branch, run=tools.gh)
        step.done.append(f"pull request #{rehearsal.pull_request} opened")
    _comment_pull_request(rehearsal, report, home, tools)
    step.done.append(f"Dancer report published on #{rehearsal.pull_request}")
    _ask_role(rehearsal, "critic", _critic_assignment(rehearsal), config, home, tools)
    step.done.append(f"critic asked to review #{rehearsal.pull_request}, round {rehearsal.round_trips + 1}")
    return step


def _after_verdict(rehearsal, verdict, text, config, home, tools):
    step = Step("wait")
    _publish_review(rehearsal, text, home, tools)
    ballet_github.update_verdicts(rehearsal.pull_request, run=tools.gh)
    step.done.append(f"verdict {verdict} published on #{rehearsal.pull_request}, Verdicts comment updated")
    if verdict == "ESCALATE":
        return Step("escalate", "the Critic escalates: see its review", step.done)
    if verdict == "APPROVED":
        premiere_step = _premiere(rehearsal, tools)
        return Step(premiere_step.next, premiere_step.reason, step.done + premiere_step.done)
    rehearsal.round_trips += 1
    if rehearsal.round_trips > config["escalation"]["max_round_trips"]:
        return Step("escalate", f"{rehearsal.round_trips} rejections, over max_round_trips", step.done)
    _ask_role(rehearsal, "dancer", _fix_assignment(rehearsal), config, home, tools)
    step.done.append(f"dancer asked to fix, round {rehearsal.round_trips + 1}")
    return step


def _premiere(rehearsal, tools):
    """Merge par rebase (le script GitHub refuse sans APPROVED frais ni CI verte), puis range le worktree."""
    if not rehearsal.pull_request:
        raise RehearsalError("no pull request to merge")
    ballet_github.merge_pull_request(rehearsal.pull_request, run=tools.gh, git=tools.git(rehearsal.repo))
    tools.orca(["worktree", "rm", "--worktree", f"path:{rehearsal.worktree}", "--delete-branch"])
    return Step("done", f"#{rehearsal.pull_request} merged on main",
                [f"#{rehearsal.pull_request} merged by rebase, {rehearsal.branch} deleted", "worktree removed"])


# --- l'état en clair ----------------------------------------------------------


def _where(rehearsal):
    return f"Rehearsal {rehearsal.id}: issue #{rehearsal.issue}, branch {rehearsal.branch}, worktree {rehearsal.worktree or 'none'}"


def _pull_request_line(rehearsal, tools):
    if not rehearsal.pull_request:
        return "no pull request yet"
    try:
        found = ballet_github.pull_request_status(rehearsal.pull_request, run=tools.gh)
    except (RehearsalError, ballet_github.GitHubError) as error:
        return f"pull request #{rehearsal.pull_request}: cannot read it ({error})"
    state = f" ({found['state'].lower()})" if found["state"] else ""
    return f"pull request #{rehearsal.pull_request}{state}: last verdict {found['verdict'] or 'none yet'}, {found['ci']}"


def _round_trips_line(rehearsal, config):
    return f"Dancer ↔ Critic round trips: {rehearsal.round_trips} of {config['escalation']['max_round_trips']}"


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
    dispatch = rehearsal.dispatches.get(role)
    if dispatch:
        tools.orca(["orchestration", "send", "--to", f"dispatch:{dispatch}",
                    "--subject", f"{rehearsal.id} · {role}", "--body", assignment])
    else:
        _start_worker(rehearsal, role, assignment, config, home, tools)


def _start_worker(rehearsal, role, assignment, config, home, tools):
    route = config["roles"][role]
    agent = ORCA_AGENTS.get(route.get("cli"))
    if not agent:
        raise RehearsalError(f"the {role}'s CLI `{route.get('cli')}` cannot run as an Orca worker yet")
    spec = _write_spec(rehearsal, role, _role_spec(rehearsal, role, assignment), home)
    arguments = ["orchestration", "worker-start", "--spec-file", str(spec), "--worktree", f"path:{rehearsal.worktree}",
                 "--agent", agent, "--task-title", f"{role.capitalize()} · {rehearsal.id}", "--json"]
    if route.get("model"):
        arguments += ["--model", route["model"]]
    rehearsal.dispatches[role] = _dispatch_id(tools.orca(arguments))


def _role_spec(rehearsal, role, assignment):
    pull_request = f", pull request #{rehearsal.pull_request}" if rehearsal.pull_request else ""
    return f"""You are the Ballet {role.capitalize()} of Rehearsal {rehearsal.id}: issue #{rehearsal.issue}{pull_request}, branch `{rehearsal.branch}`, in this worktree.

Load the skill `/ballet:{role}` and follow it. Its GitHub script is {SKILLS_ROOT.parent / "scripts" / "ballet_github.py"}.

{assignment}

Under the Conductor:
- A question: one Ballet message (`templates/message.md`, `type: question`), sent with `orca orchestration ask --question "<the whole message>"`. Then end your turn: the answer comes back here, in this session.
- When you are done: your final message, whole, header line first, is the body of your `worker_done`.
- Never push, never run `gh`, never change branch (spikes excepted, for the Choreographer).
"""


def _first_assignment(role, rehearsal):
    if role == "dancer":
        return f"Execute your repo's section of the plan of issue #{rehearsal.issue}, task by task."
    return f"Issue #{rehearsal.issue} has no plan yet: write it (`plan`), commit your ADRs on this branch, then report."


def _critic_assignment(rehearsal):
    return (f"Review pull request #{rehearsal.pull_request} of issue #{rehearsal.issue}, round {rehearsal.round_trips + 1}: "
            f"the branch `{rehearsal.branch}` against the plan.")


def _fix_assignment(rehearsal):
    return (f"Round {rehearsal.round_trips + 1}: the Critic rejected pull request #{rehearsal.pull_request}. "
            f"Read its review (`read-pr {rehearsal.pull_request}`), fix each blocking point, then report again.")


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
    """Le script GitHub publie depuis un fichier : le message passe par `.ballet/run/outbox.md`."""
    outbox = _run_dir(home) / "outbox.md"
    outbox.write_text(text, encoding="utf-8")
    return outbox


def _write_spec(rehearsal, role, spec, home):
    folder = _run_dir(home) / rehearsal.id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{role}-{len(list(folder.glob(f'{role}-*.md'))) + 1}.md"
    path.write_text(spec, encoding="utf-8")
    return path


def _settle(rehearsal, step, home):
    """Le pas fixe le statut de la Rehearsal ; l'état est sauvé et le pas journalisé."""
    rehearsal.status = STATUS_OF_STEP[step.next]
    rehearsal.reason = step.reason
    _save(rehearsal, home)
    _log(home, rehearsal, step.next, {"reason": step.reason, "done": step.done})
    return step


def _save(rehearsal, home):
    _state_path(rehearsal.id, home).write_text(json.dumps(asdict(rehearsal), indent=2) + "\n", encoding="utf-8")


def _load(rehearsal_id, home):
    path = _state_path(rehearsal_id, home)
    if not path.is_file():
        raise RehearsalError(f"no Rehearsal {rehearsal_id} in {path.parent}")
    return Rehearsal(**json.loads(path.read_text(encoding="utf-8")))


def _refuse_if_already_open(rehearsal, home):
    path = _state_path(rehearsal.id, home)
    if path.is_file() and json.loads(path.read_text(encoding="utf-8"))["status"] != "done":
        raise RehearsalError(f"Rehearsal {rehearsal.id} is already open ({path})")


def _log(home, rehearsal, event, detail):
    entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rehearsal": rehearsal.id, "event": event, "detail": detail}
    with (_run_dir(home) / "journal.jsonl").open("a", encoding="utf-8") as journal:
        journal.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _state_path(rehearsal_id, home):
    return _run_dir(home) / f"{rehearsal_id}.json"


def _run_dir(home):
    folder = Path(home) / RUN_DIR
    folder.mkdir(parents=True, exist_ok=True)
    return folder


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
    plan = body.split("\n## Plan\n", 1)[1] if "\n## Plan\n" in f"\n{body}" else ""
    return bool(re.search(r"^- \[[ x]\] ", plan, re.MULTILINE))


def _message(path):
    try:
        return read_message(path)
    except MessageError as error:
        raise RehearsalError(f"invalid message, send it back to its author: {error}") from error


def _open_worktree(rehearsal, tools):
    git = tools.git(rehearsal.repo)
    git(["fetch", "origin", "main"])
    tools.orca(["worktree", "create", "--name", rehearsal.branch.replace("/", "-").replace(".", "-"),
                "--repo", f"path:{rehearsal.repo}", "--base-branch", "origin/main", "--branch", rehearsal.branch,
                "--issue", rehearsal.issue, "--no-parent", "--json"])
    return _worktree_of(rehearsal.branch, git(["worktree", "list", "--porcelain"]))


def _worktree_of(branch, porcelain):
    path = None
    for line in porcelain.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):]
        elif line == f"branch refs/heads/{branch}":
            return path
    raise RehearsalError(f"no worktree found for {branch} after its creation")


def _dispatch_id(output):
    """Le dispatch du worker, où qu'il soit dans le reçu JSON d'Orca."""
    found = _find_key(json.loads(output), "dispatchId")
    if not found:
        raise RehearsalError("the worker started but its receipt names no dispatchId")
    return found


def _find_key(value, key):
    if isinstance(value, dict):
        if isinstance(value.get(key), str):
            return value[key]
        value = list(value.values())
    if isinstance(value, list):
        return next((found for item in value if (found := _find_key(item, key))), None)
    return None


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
        print(_command(command, arguments, home, tools))
    except UsageError as error:
        print(error, file=sys.stderr)
        return 2
    except (RehearsalError, ballet_github.GitHubError) as error:
        print(Step("escalate", str(error)).render())
    return 0


def _command(command, arguments, home, tools):
    if command == "begin" and len(arguments) == 1:
        return begin(arguments[0], home, tools).render()
    if command == "receive" and len(arguments) in (2, 4) and arguments[2:3] in ([], ["--question"]):
        return receive(arguments[0], arguments[1], arguments[3] if len(arguments) == 4 else None, home, tools).render()
    if command == "premiere" and len(arguments) == 1:
        return premiere(arguments[0], home, tools).render()
    if command == "status" and len(arguments) == 1:
        return status(arguments[0], home, tools).render()
    if command == "status" and arguments[1:] == ["--json"]:
        return json.dumps(asdict(_load(arguments[0], home)), indent=2)
    raise UsageError("usage: begin <issue> | receive <ID> <message.md> [--question <msg-id>] | premiere <ID> | status <ID> [--json]")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
