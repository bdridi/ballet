"""Le programme : ce que la file GitHub attend de la prochaine Rehearsal.

    python3 ballet_program.py [<dossier>]      # le repo GitHub de ce dossier (par défaut : le dossier courant)

Lecture seule. Le programme, ce sont les issues ouvertes du repo dont le type est `Feature`, `Bug` ou `Task` et dont
le champ `Ballet status` vaut `ready` ; les `Slice` n'y figurent pas, elles suivent leur feature. L'ordre est celui du
champ `Priority` (Urgent, High, Medium, Low, puis sans priorité), puis l'ancienneté.
"""

import json
import subprocess
import sys
from pathlib import Path

QUEUED_TYPES = ("Feature", "Bug", "Task")
READY = "ready"
STATUS_FIELD = "Ballet status"
MODE_FIELD = "Rehearsal mode"
PRIORITY_FIELD = "Priority"
PRIORITIES = ("Urgent", "High", "Medium", "Low")
OPEN_ISSUES = """query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    issues(first: 100, states: OPEN, after: $after, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title createdAt issueType { name }
        issueFieldValues(first: 20) { nodes {
          ... on IssueFieldSingleSelectValue { name field { ... on IssueFieldSingleSelect { name } } }
        } }
      }
    }
  }
}"""


class ProgramError(Exception):
    """GitHub n'a pas répondu : le programme est inconnu, pas vide."""


def ready_items(project_dir=".", run=None):
    """Les éléments prêts de la file, dans l'ordre où ils se jouent."""
    run = run or _gh_in(project_dir)
    issues = _open_issues(run)
    ready = [_item_of(issue) for issue in issues if _is_ready(issue)]
    return sorted(ready, key=_playing_order)


def main(argv):
    project_dir = argv[1] if len(argv) > 1 else "."
    try:
        items = ready_items(project_dir)
    except ProgramError as error:
        print(f"✗ GitHub program: {error}", file=sys.stderr)
        return 1
    print_program(items)
    return 0


def print_program(items):
    if not items:
        print("the program is empty: no Feature, Bug or Task is ready")
    for position, item in enumerate(items, start=1):
        print(f"{position:>2}. {item['item']:<6} {item['type']:<8} {item['priority'] or '-':<7} {item['title']}")


# --- étapes -----------------------------------------------------------------


def _open_issues(run):
    issues, cursor = [], ""
    while True:
        page = _read_page(cursor, run)
        issues += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return issues
        cursor = page["pageInfo"]["endCursor"]


def _is_ready(issue):
    return _type_of(issue) in QUEUED_TYPES and _field(issue, STATUS_FIELD) == READY


def _item_of(issue):
    return {
        "item": f"#{issue['number']}",
        "number": issue["number"],
        "title": issue["title"],
        "type": _type_of(issue),
        "priority": _field(issue, PRIORITY_FIELD),
        "mode": _field(issue, MODE_FIELD),
        "created_at": issue["createdAt"],
    }


def _playing_order(item):
    return (_priority_rank(item["priority"]), item["created_at"])


# --- lecture ----------------------------------------------------------------


def _read_page(cursor, run):
    arguments = ["api", "graphql", "-f", f"query={OPEN_ISSUES}", "-F", "owner={owner}", "-F", "name={repo}"]
    if cursor:
        arguments += ["-F", f"after={cursor}"]
    answer = json.loads(run(arguments))
    if answer.get("errors"):
        raise ProgramError(answer["errors"][0]["message"])
    return answer["data"]["repository"]["issues"]


def _type_of(issue):
    return (issue.get("issueType") or {}).get("name", "")


def _field(issue, name):
    """La valeur d'un champ à choix unique ; vide s'il n'est pas posé sur l'issue."""
    for value in issue["issueFieldValues"]["nodes"]:
        if value and (value.get("field") or {}).get("name") == name:
            return value["name"]
    return ""


def _priority_rank(priority):
    return PRIORITIES.index(priority) if priority in PRIORITIES else len(PRIORITIES)


def _gh_in(project_dir):
    def run(arguments):
        try:
            completed = subprocess.run(["gh", *arguments], capture_output=True, text=True, cwd=Path(project_dir), timeout=15)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ProgramError(f"gh did not answer ({error})")
        if completed.returncode != 0:
            raise ProgramError(completed.stderr.strip() or f"gh {arguments[0]} failed")
        return completed.stdout
    return run


if __name__ == "__main__":
    sys.exit(main(sys.argv))
