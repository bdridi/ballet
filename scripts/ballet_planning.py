"""Prépare la planification GitHub dont vit la file : les types et les champs d'issue du propriétaire du repo.

    python3 ballet_planning.py [<dossier>]      # le repo GitHub de ce dossier (par défaut : le dossier courant)

Types et champs appartiennent au propriétaire du repo (compte personnel ou organisation) et valent pour tous
ses repos : un deuxième projet du même propriétaire les trouve déjà là. Le script ne crée que ce qui manque ;
il ne modifie ni ne supprime jamais rien. Un champ qui existe sans toutes ses options est signalé, à compléter
à la main (Settings → Planning).

Ce qu'il faut à la file :
- les types `Task`, `Bug`, `Feature` (là par défaut) et `Slice` ;
- le champ `Ballet status` : où en est l'issue dans la file (`Status` est un nom réservé par GitHub) ;
- le champ `Rehearsal mode` : comment la Rehearsal tourne (`assisted`, `autopilot`) ;
- le champ `Size` : la taille du ticket (`S` : sans plan, le Dancer part de l'issue ; `M` : planifiée) ; vide, `S` pour un bug ou une tâche, `M` pour une feature ;
- le champ `Plan approval` : si le plan attend le Director (`required`, `skipped`) ; vide, le profil décide ;
- le champ `Priority` : l'ordre de la file, puis l'ancienneté.

Un compte personnel demande le droit `user` au jeton de `gh` (`gh auth refresh -h github.com -s user`) ;
une organisation, d'en être administrateur.
"""

import json
import subprocess
import sys
from pathlib import Path

ISSUE_TYPES = (
    ("Task", "A piece of work with no new visible behaviour.", "YELLOW"),
    ("Bug", "A gap between the spec and the product.", "RED"),
    ("Feature", "A visible behaviour, framed in the Workshop.", "BLUE"),
    ("Slice", "A part of a feature, played as its own Rehearsal.", "PURPLE"),
)

ISSUE_FIELDS = (
    ("Ballet status", "Where the issue stands in Ballet's queue.", (
        ("proposed", "GRAY", "Proposed by the Workshop in autopilot: waits for the Director's yes."),
        ("ready", "BLUE", "In the queue: the next Rehearsal can take it."),
        ("in-rehearsal", "YELLOW", "A Rehearsal is playing it."),
        ("plan-review", "PURPLE", "The plan waits for the Director's approval."),
        ("escalated", "RED", "Waits for the Director's decision."),
        ("done", "GREEN", "Merged on main (Premiere)."),
    )),
    ("Rehearsal mode", "How its Rehearsal runs; empty means assisted.", (
        ("assisted", "BLUE", "The Director gets the escalations."),
        ("autopilot", "GREEN", "Without the Director: each role decides within its perimeter."),
    )),
    ("Size", "How big the ticket is; empty means M.", (
        ("S", "GREEN", "No plan: the Dancer starts from the issue and its analogue."),
        ("M", "BLUE", "Planned by the Choreographer, sliced when it is too big."),
    )),
    ("Plan approval", "In assisted, whether the plan waits for the Director; empty means the project's profile.", (
        ("required", "PURPLE", "The plan waits for the Director's approval before any code."),
        ("skipped", "GRAY", "The Dancer starts on the plan as soon as it is published."),
    )),
    ("Priority", "The queue's order, before age.", (
        ("Urgent", "RED", ""),
        ("High", "ORANGE", ""),
        ("Medium", "YELLOW", ""),
        ("Low", "GRAY", ""),
    )),
)

FIELD_NAMES = """
  issueFields(first: 50) { nodes {
    ... on IssueFieldSingleSelect { name options { name } }
    ... on IssueFieldText { name }
    ... on IssueFieldNumber { name }
    ... on IssueFieldDate { name }
  } }"""
READ_OWNER = f"""query($owner: String!) {{ repositoryOwner(login: $owner) {{
  __typename id login
  ... on User {{ issueTypes(first: 50) {{ nodes {{ name }} }} {FIELD_NAMES} }}
  ... on Organization {{ issueTypes(first: 50) {{ nodes {{ name }} }} {FIELD_NAMES} }}
}} }}"""
CREATE_TYPE = "mutation {{ createIssueType(input: {{ownerId: {owner}, name: {name}, description: {description}, color: {color}, isEnabled: true}}) {{ issueType {{ id }} }} }}"
CREATE_FIELD = "mutation {{ createIssueField(input: {{ownerId: {owner}, name: {name}, description: {description}, dataType: SINGLE_SELECT, options: [{options}]}}) {{ issueField {{ ... on IssueFieldSingleSelect {{ id }} }} }} }}"
NEXT_GLOBAL_ID = "X-Github-Next-Global-ID: 1"  # l'ancien format d'ID du propriétaire est déprécié
MISSING_SCOPE_HINT = "a personal account needs the `user` scope: gh auth refresh -h github.com -s user"


class PlanningError(Exception):
    """GitHub a refusé une lecture ou une création."""


def prepare(project_dir=".", run=None):
    """Crée ce qui manque chez le propriétaire du repo ; renvoie ce qui a été créé, gardé, ou reste incomplet."""
    run = run or _gh_in(project_dir)
    owner = _read_owner(run)
    report = {"owner": owner["login"], "created": [], "kept": [], "incomplete": []}
    _ensure_issue_types(owner, report, run)
    _ensure_issue_fields(owner, report, run)
    return report


def main(argv):
    project_dir = argv[1] if len(argv) > 1 else "."
    try:
        report = prepare(project_dir)
    except PlanningError as error:
        print(f"✗ GitHub planning: {error}", file=sys.stderr)
        return 1
    print_report(report)
    return 0


def print_report(report):
    for name in report["created"]:
        print(f"created        {name} ({report['owner']})")
    for name in report["kept"]:
        print(f"already exists {name} ({report['owner']}, unchanged)")
    for name, missing in report["incomplete"]:
        print(f"incomplete     {name}: missing options {', '.join(missing)} (add them in Settings → Planning)")


# --- étapes -----------------------------------------------------------------


def _read_owner(run):
    output = run(["api", "graphql", "-H", NEXT_GLOBAL_ID, "-f", f"query={READ_OWNER}", "-F", "owner={owner}"])
    owner = json.loads(output)["data"]["repositoryOwner"]
    return {
        "id": owner["id"],
        "login": owner["login"],
        "types": {node["name"] for node in owner["issueTypes"]["nodes"]},
        "fields": {node["name"]: _option_names(node) for node in owner["issueFields"]["nodes"] if node},
    }


def _ensure_issue_types(owner, report, run):
    for name, description, color in ISSUE_TYPES:
        if name in owner["types"]:
            report["kept"].append(f"issue type {name}")
            continue
        _mutate(CREATE_TYPE.format(owner=_quoted(owner["id"]), name=_quoted(name), description=_quoted(description), color=color), run)
        report["created"].append(f"issue type {name}")


def _ensure_issue_fields(owner, report, run):
    for name, description, options in ISSUE_FIELDS:
        if name not in owner["fields"]:
            _mutate(CREATE_FIELD.format(owner=_quoted(owner["id"]), name=_quoted(name), description=_quoted(description), options=_options(options)), run)
            report["created"].append(f"issue field {name}")
            continue
        report["kept"].append(f"issue field {name}")
        missing = [option for option, _, _ in options if option not in owner["fields"][name]]
        if missing:
            report["incomplete"].append((f"issue field {name}", missing))


# --- outils -----------------------------------------------------------------


def _options(options):
    return ", ".join(
        f"{{name: {_quoted(name)}, color: {color}, description: {_quoted(description)}, priority: {position}}}"
        for position, (name, color, description) in enumerate(options, start=1)
    )


def _option_names(node):
    return {option["name"] for option in node.get("options", [])}


def _quoted(text):
    """Une chaîne GraphQL : même échappement qu'une chaîne JSON."""
    return json.dumps(text)


def _mutate(mutation, run):
    output = run(["api", "graphql", "-f", f"query={mutation}"])
    errors = json.loads(output).get("errors")
    if errors:
        raise PlanningError(_explained(errors[0]["message"]))


def _explained(message):
    if "permission" in message.lower():
        return f"{message} ({MISSING_SCOPE_HINT})"
    return message


def _gh_in(project_dir):
    def run(arguments):
        completed = subprocess.run(["gh", *arguments], capture_output=True, text=True, cwd=Path(project_dir))
        if completed.returncode != 0:
            raise PlanningError(_explained(completed.stderr.strip() or f"gh {arguments[0]} failed"))
        return completed.stdout
    return run


if __name__ == "__main__":
    sys.exit(main(sys.argv))
