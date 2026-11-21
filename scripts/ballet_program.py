"""Le programme : ce que la file GitHub attend de la prochaine Rehearsal.

    python3 ballet_program.py [<dossier>]      # le repo GitHub de ce dossier (par défaut : le dossier courant)

Lecture seule. Le programme, ce sont les issues ouvertes du repo dont le type est `Feature`, `Bug` ou `Task` et dont
le champ `Ballet status` vaut `ready` ; les `Slice` n'y figurent pas, elles suivent leur feature. L'ordre est celui du
champ `Priority` (Urgent, High, Medium, Low, puis sans priorité), puis l'ancienneté.

Les dépendances sont les liens natifs de GitHub (« Blocked by »), lus dans la même requête : un seul calcul, que la Scène,
le Monitor, Maestro et le lanceur lisent tous. Chaque élément prêt porte :

- `blocked_by` : ses bloqueurs encore ouverts (`item` : `#M`, ou `<repo>#M` quand le bloqueur est dans un autre repo ; `number`,
  `repo`, `url`) ;
- `launchable` : vrai quand il n'en a aucun. Il ne part que si tous ses bloqueurs sont fermés ;
- `doubt` : ce qui rend la dépendance douteuse et ne se tranche que par le Director, sinon vide : un bloqueur fermé sans avoir été
  livré (*not planned*, doublon), un cycle de dépendances (dans le repo), un bloqueur illisible (repo inaccessible, ou trop nombreux).

Un élément **attend** (`waits`) quand il a un bloqueur ouvert sans doute : un cycle ou un bloqueur illisible ne se résout pas en attendant.
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

QUEUED_TYPES = ("Feature", "Bug", "Task")
READY = "ready"
STATUS_FIELD = "Ballet status"
MODE_FIELD = "Rehearsal mode"
PRIORITY_FIELD = "Priority"
PRIORITIES = ("Urgent", "High", "Medium", "Low")
UNDELIVERED_REASONS = ("NOT_PLANNED", "DUPLICATE")   # une issue fermée sans que son travail soit fait
MAX_BLOCKERS = 20   # les bloqueurs lus par issue ; au-delà, la dépendance est douteuse (illisible)
OPEN_ISSUES = """query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    issues(first: 100, states: OPEN, after: $after, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title url createdAt issueType { name }
        blockedBy(first: 20) { totalCount nodes { number state stateReason url repository { nameWithOwner } } }
        issueFieldValues(first: 20) { nodes {
          ... on IssueFieldSingleSelectValue { name field { ... on IssueFieldSingleSelect { name } } }
        } }
      }
    }
  }
}"""


class ProgramError(Exception):
    """GitHub n'a pas répondu : le programme est inconnu, pas vide."""


@dataclass
class Queue:
    """Les issues ouvertes d'un repo, et qui y bloque qui (les liens « Blocked by » entre issues ouvertes du même repo)."""
    repo: str
    issues: list
    open_blockers: dict


def ready_items(project_dir=".", run=None):
    """Les éléments prêts de la file, dans l'ordre où ils se jouent, chacun avec ses bloqueurs encore ouverts."""
    queue = _read_queue(run or _gh_in(project_dir))
    ready = [_item_of(issue, queue) for issue in queue.issues if _is_ready(issue)]
    return sorted(ready, key=_playing_order)


def dependencies_of(number, project_dir=".", run=None):
    """Les bloqueurs ouverts et le doute d'une issue ouverte du repo, prête ou non (le même calcul que `ready_items`).
    Une issue fermée ou inconnue n'a aucune dépendance."""
    queue = _read_queue(run or _gh_in(project_dir))
    issue = next((found for found in queue.issues if found["number"] == int(number)), None)
    return _dependencies(issue, queue) if issue else {"blocked_by": [], "doubt": ""}


def waits(item):
    """L'élément attend : un bloqueur ouvert, et rien de douteux (un cycle ou un bloqueur illisible ne se résout pas en attendant)."""
    return bool(item.get("blocked_by")) and not item.get("doubt")


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
        print(f"{position:>2}. {item['item']:<6} {item['type']:<8} {item['priority'] or '-':<7} {item['title']}{_dependency_note(item)}")


# --- étapes -----------------------------------------------------------------


def _read_queue(run):
    repo, issues = _open_issues(run)
    return Queue(repo, issues, {issue["number"]: _same_repo_open_blockers(issue, repo) for issue in issues})


def _open_issues(run):
    issues, cursor = [], ""
    while True:
        repository = _read_page(cursor, run)
        page = repository["issues"]
        issues += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return repository.get("nameWithOwner", ""), issues
        cursor = page["pageInfo"]["endCursor"]


def _is_ready(issue):
    return _type_of(issue) in QUEUED_TYPES and _field(issue, STATUS_FIELD) == READY


def _item_of(issue, queue):
    dependencies = _dependencies(issue, queue)
    return {
        "item": f"#{issue['number']}",
        "number": issue["number"],
        "title": issue["title"],
        "url": issue["url"],
        "type": _type_of(issue),
        "priority": _field(issue, PRIORITY_FIELD),
        "mode": _field(issue, MODE_FIELD),
        "created_at": issue["createdAt"],
        "blocked_by": dependencies["blocked_by"],
        "launchable": not dependencies["blocked_by"],
        "doubt": dependencies["doubt"],
    }


def _playing_order(item):
    return (_priority_rank(item["priority"]), item["created_at"])


# --- les dépendances -----------------------------------------------------------


def _dependencies(issue, queue):
    blockers = _readable_blockers(issue)
    return {
        "blocked_by": [_blocker_of(blocker, queue.repo) for blocker in blockers if blocker["state"] == "OPEN"],
        "doubt": _unreadable_doubt(issue, blockers) or _undelivered_doubt(blockers, queue.repo) or _cycle_doubt(issue, queue),
    }


def _readable_blockers(issue):
    return [blocker for blocker in (issue.get("blockedBy") or {}).get("nodes", []) if blocker]


def _unreadable_doubt(issue, readable):
    """GitHub compte plus de bloqueurs que d'entrées lisibles : un repo inaccessible, ou plus que `MAX_BLOCKERS`.
    Le compte est `blockedBy.totalCount`, à jour tout de suite ; `issueDependenciesSummary` a plusieurs secondes de retard
    (vérifié en vrai) et ferait voir un bloqueur illisible juste après un `unblock`."""
    total = (issue.get("blockedBy") or {}).get("totalCount", len(readable))
    if total > len(readable):
        return f"{total - len(readable)} of its {total} blockers cannot be read (inaccessible repo, or more than {MAX_BLOCKERS})"
    return ""


def _undelivered_doubt(blockers, repo):
    """Un bloqueur fermé sans avoir été livré (*not planned*, doublon) : sa fermeture ne dit pas que le travail est fait."""
    for blocker in blockers:
        if blocker["state"] == "CLOSED" and blocker.get("stateReason") in UNDELIVERED_REASONS:
            reason = blocker["stateReason"].lower().replace("_", " ")
            return f"blocker {_blocker_of(blocker, repo)['item']} was closed as {reason}, not delivered"
    return ""


def _cycle_doubt(issue, queue):
    path = _cycle_through(issue["number"], queue.open_blockers)
    return "dependency cycle: " + " → ".join(f"#{number}" for number in path) if path else ""


def _cycle_through(start, open_blockers):
    """Le chemin qui part de `start`, suit « est bloqué par » et y revient ; vide quand il n'y a pas de cycle."""
    pending, seen = [(start, [start])], set()
    while pending:
        number, path = pending.pop()
        for blocker in open_blockers.get(number, []):
            if blocker == start:
                return [*path, start]
            if blocker not in seen:
                seen.add(blocker)
                pending.append((blocker, [*path, blocker]))
    return []


def _same_repo_open_blockers(issue, repo):
    return [blocker["number"] for blocker in _readable_blockers(issue)
            if blocker["state"] == "OPEN" and blocker["repository"]["nameWithOwner"] == repo]


def _blocker_of(blocker, repo):
    found = blocker["repository"]["nameWithOwner"]
    return {"item": f"#{blocker['number']}" if found == repo else f"{found}#{blocker['number']}",
            "number": blocker["number"], "repo": found, "url": blocker["url"]}


def _dependency_note(item):
    if item["doubt"]:
        return f"  [ask the Director: {item['doubt']}]"
    if item["blocked_by"]:
        return "  [blocked by " + ", ".join(blocker["item"] for blocker in item["blocked_by"]) + "]"
    return ""


# --- lecture ----------------------------------------------------------------


def _read_page(cursor, run):
    arguments = ["api", "graphql", "-f", f"query={OPEN_ISSUES}", "-F", "owner={owner}", "-F", "name={repo}"]
    if cursor:
        arguments += ["-F", f"after={cursor}"]
    answer = json.loads(run(arguments))
    if answer.get("errors"):
        raise ProgramError(answer["errors"][0]["message"])
    return answer["data"]["repository"]


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
