"""Le seul point de passage vers GitHub : une liste fermée d'opérations sur les issues et les PR.

    python3 ballet_github.py read    <issue>                     # affiche le corps de l'issue
    python3 ballet_github.py publish <brouillon.md>              # crée l'issue, affiche son numéro
    python3 ballet_github.py plan    <issue> <plan.md>           # écrit la section ## Plan de l'issue
    python3 ballet_github.py slice   <parente> <brouillon.md>    # crée l'issue d'une slice, liée à sa parente
    python3 ballet_github.py read-pr <pr>                        # affiche la PR, ses reviews et ses commentaires, dans l'ordre

Le repo GitHub est celui du dossier courant (celui que `gh` déduit du remote).
Le titre d'une issue est le premier titre `# …` de son brouillon ; le corps, tout le reste.
"""

import json
import subprocess
import sys
from pathlib import Path

PLAN_HEADING = "## Plan"


class GitHubError(Exception):
    """Une opération est refusée, ou `gh` a échoué."""


def read_issue(number, run=None):
    return _issue_body(number, run or _run_gh)


def publish_issue(draft_path, run=None):
    title, body = _title_and_body(_read_draft(draft_path))
    return _create_issue(title, body, run or _run_gh)


def write_plan(number, plan_path, run=None):
    run = run or _run_gh
    body = _issue_body(number, run)
    plan = _plan_only(_read_draft(plan_path))
    _edit_issue(number, _with_plan(body, plan), run)


def publish_slice(parent_number, draft_path, run=None):
    title, body = _title_and_body(_read_draft(draft_path))
    return _create_issue(title, _linked_to_parent(body, parent_number), run or _run_gh)


def read_pull_request(number, run=None):
    number = _issue_number(number)
    pull_request = _pull_request(number, run or _run_gh)
    return _as_markdown(number, pull_request)


def main(argv):
    operation, arguments = (argv[1], argv[2:]) if len(argv) > 1 else (None, [])
    try:
        result = _dispatch(operation, arguments)
    except GitHubError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    if result is not None:
        print(result)
    return 0


# --- opérations -------------------------------------------------------------


def _dispatch(operation, arguments):
    operations = {
        "read": (read_issue, 1),
        "publish": (publish_issue, 1),
        "plan": (write_plan, 2),
        "slice": (publish_slice, 2),
        "read-pr": (read_pull_request, 1),
    }
    if operation not in operations:
        raise GitHubError(f"unknown operation '{operation}'; known: {', '.join(operations)}")
    function, arity = operations[operation]
    if len(arguments) != arity:
        raise GitHubError(f"{operation} expects {arity} argument(s)")
    return function(*arguments)


def _issue_body(number, run):
    output = run(["issue", "view", _issue_number(number), "--json", "body"])
    return json.loads(output)["body"]


def _pull_request(number, run):
    output = run(["pr", "view", number, "--json", "title,body,reviews,comments"])
    return json.loads(output)


def _create_issue(title, body, run):
    url = run(["issue", "create", "--title", title, "--body", body]).strip()
    return url.rsplit("/", 1)[-1]


def _edit_issue(number, body, run):
    run(["issue", "edit", _issue_number(number), "--body", body])


# --- texte des issues -------------------------------------------------------


def _as_markdown(number, pull_request):
    header = f"# PR #{number} · {pull_request['title']}\n\n{pull_request['body'].strip()}\n"
    entries = sorted(_reviews(pull_request) + _comments(pull_request))
    return header + "".join(f"\n## {heading}\n\n{body.strip()}\n" for _, heading, body in entries)


def _reviews(pull_request):
    return [
        (review["submittedAt"], f"Review · {review['author']['login']} · {review['submittedAt']}", review["body"])
        for review in pull_request.get("reviews", [])
    ]


def _comments(pull_request):
    return [
        (comment["createdAt"], f"Comment · {comment['author']['login']} · {comment['createdAt']}", comment["body"])
        for comment in pull_request.get("comments", [])
    ]


def _read_draft(path):
    path = Path(path)
    if not path.is_file():
        raise GitHubError(f"file not found: {path}")
    return path.read_text(encoding="utf-8")


def _title_and_body(text):
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# "):
            body = "\n".join(lines[index + 1:]).strip() + "\n"
            return line[2:].strip(), body
    raise GitHubError("the draft has no `# …` title; a file holding only the ## Plan section goes to `plan`")


def _plan_only(text):
    if any(line.startswith("# ") for line in text.splitlines()):
        raise GitHubError("this is a full issue draft (`# …` title); `plan` expects only the ## Plan section, a draft goes to `publish` or `slice`")
    return text


def _with_plan(body, plan):
    """Remplace le contenu de la section ## Plan, jusqu'au titre ## suivant."""
    lines = body.splitlines()
    if PLAN_HEADING not in lines:
        raise GitHubError(f"the issue has no '{PLAN_HEADING}' section")
    start = lines.index(PLAN_HEADING) + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    section = ["", _without_plan_heading(plan).strip(), ""]
    return "\n".join(lines[:start] + section + lines[end:]).rstrip() + "\n"


def _without_plan_heading(plan):
    lines = plan.strip().splitlines()
    return "\n".join(lines[1:]) if lines and lines[0].strip() == PLAN_HEADING else plan


def _linked_to_parent(body, parent_number):
    return f"Part of #{_issue_number(parent_number)}\n\n{body}"


# --- gh ---------------------------------------------------------------------


def _issue_number(value):
    number = str(value).lstrip("#")
    if not number.isdigit():
        raise GitHubError(f"invalid issue or PR number: {value}")
    return number


def _run_gh(arguments):
    completed = subprocess.run(["gh", *arguments], capture_output=True, text=True)
    if completed.returncode != 0:
        raise GitHubError(completed.stderr.strip() or f"gh {arguments[0]} failed")
    return completed.stdout


if __name__ == "__main__":
    sys.exit(main(sys.argv))
