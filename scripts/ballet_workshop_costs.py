"""Le coût des Workshops assisted (OPP-95) : les notes `ballet:cost` des issues, rangées dans la base par le Monitor, lues
par la Scène.

    python3 ballet_workshop_costs.py sweep <projet>    # un passage à la main : une page d'issues du projet

Le Dramaturg d'un Workshop assisted publie ses issues en ligne de commande ; `publish` y laisse le coût de sa session
(`ballet_cost.render_cost_note`, `kind: workshop-assisted`). La Scène ne lit jamais GitHub : le Monitor, à chaque tour, lit
ici les issues de chaque projet mises à jour depuis sa marque (`workshop_cost_watermarks`, une par projet), une page de
`PAGE_SIZE` issues au plus, dans l'ordre de mise à jour, et n'en garde que les commentaires qui portent `<!-- ballet:cost`.
Chaque note est relue par `ballet_cost.parse_cost_note` et rangée dans `workshop_costs`, une ligne par tranche (projet,
session, segment) ; une note illisible va dans `workshop_cost_problems` (`format v2`, `malformed`), sans arrêter le passage.
Les notes et la marque s'écrivent dans la même transaction : la marque n'avance qu'une fois la page rangée, et relire une
page ne change rien. Un gros arriéré se rattrape en quelques tours, jamais en un tour lent.

`read` rend à la Scène les sessions les plus récentes (`SHOWN` au plus) : chaque tranche une fois, leur total, les tranches
manquantes (`segment N: cost unknown`, jamais 0), et les notes illisibles.
"""

import json
import subprocess
import sys

import ballet_cost
import ballet_db
import ballet_maestro

PAGE_SIZE = 50           # les issues lues par projet et par tour : un arriéré se rattrape sur plusieurs tours
COMMENTS_READ = 30       # la note est postée juste après la création de l'issue : parmi ses premiers commentaires
SHOWN = 200              # les sessions que la Scène reçoit, les plus récentes : la page ne grossit pas avec les issues
BEGINNING = "1970-01-01T00:00:00Z"
MARKER = "<!-- ballet:cost"
ISSUES_SINCE = """query($owner: String!, $name: String!, $since: DateTime!, $first: Int!, $comments: Int!) {
  repository(owner: $owner, name: $name) {
    issues(first: $first, orderBy: {field: UPDATED_AT, direction: ASC}, filterBy: {since: $since}) {
      nodes { number title updatedAt comments(first: $comments) { nodes { id body } } }
    }
  }
}"""


class WorkshopCostError(Exception):
    """GitHub n'a pas répondu : une ligne d'erreur du tour du Monitor, la marque ne bouge pas."""


def sweep(project, home, state=None, run=None, page_size=PAGE_SIZE):
    """Un passage sur un projet : la page d'issues suivante, ses notes rangées, la marque avancée ; rend ce qui a été lu."""
    since = watermark(project, state)
    issues = _issues_updated_since(since, home, run or _run_gh, page_size)
    if not issues:
        return f"{project}: no issue updated since {since}"
    notes, problems = _notes_of(issues)
    _store(project, notes, problems, issues[-1]["updatedAt"], state)
    return f"{project}: {len(issues)} issue(s) read, {len(notes)} cost note(s), {len(problems)} unreadable"


def watermark(project, state=None):
    """Jusqu'où les issues du projet ont été lues ; le début des temps pour un projet jamais lu."""
    with ballet_db.reading(state) as connection:
        row = connection.execute("SELECT updated_since FROM workshop_cost_watermarks WHERE project = ?", (project,)).fetchone()
    return row["updated_since"] if row else BEGINNING


def read(state=None, shown=SHOWN):
    """Pour la Scène : `{sessions, unreadable}`, les sessions de Workshop assisted les plus récentes d'abord."""
    with ballet_db.reading(state) as connection:
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM workshop_costs WHERE (project, session) IN (SELECT project, session FROM workshop_costs "
            "GROUP BY project, session ORDER BY max(ended_at) DESC LIMIT ?) ORDER BY segment", (shown,))]
        problems = [dict(row) for row in connection.execute("SELECT * FROM workshop_cost_problems ORDER BY project, issue")]
    sessions = _sessions_of(rows)
    return {"sessions": sorted(sessions, key=lambda session: session["to"], reverse=True),
            "unreadable": [{"project": row["project"], "item": f"#{row['issue']}", "title": row["title"],
                            "problem": f"cost unreadable ({row['problem']})"} for row in problems]}


# --- la lecture de GitHub -------------------------------------------------------------------------------------------


def _issues_updated_since(since, home, run, page_size):
    arguments = ["api", "graphql", "-f", f"query={ISSUES_SINCE}", "-F", "owner={owner}", "-F", "name={repo}",
                 "-f", f"since={since}", "-F", f"first={page_size}", "-F", f"comments={COMMENTS_READ}"]
    try:
        answer = json.loads(run(arguments, home))
    except ValueError as error:
        raise WorkshopCostError(f"gh answered something that is not JSON: {error}") from error
    if answer.get("errors"):
        raise WorkshopCostError(answer["errors"][0].get("message", "gh refused the query"))
    return ((answer.get("data") or {}).get("repository") or {}).get("issues", {}).get("nodes") or []


def _run_gh(arguments, home):
    try:
        done = subprocess.run(["gh", *arguments], cwd=home, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise WorkshopCostError(f"gh did not answer: {error}") from error
    if done.returncode != 0:
        raise WorkshopCostError(f"gh did not answer: {done.stderr.strip()}")
    return done.stdout


def _notes_of(issues):
    """Les notes lisibles et les illisibles, dans les commentaires qui portent la marque ; les autres ne sont pas lus."""
    notes, problems = [], []
    for issue in issues:
        for comment in (issue.get("comments") or {}).get("nodes") or []:
            body = comment.get("body") or ""
            if MARKER not in body:
                continue
            note = ballet_cost.parse_cost_note(body)
            if note:
                notes.append((issue, note))
            else:
                problems.append((issue, comment.get("id", ""), ballet_cost.cost_note_problem(body) or "malformed"))
    return notes, problems


# --- la base --------------------------------------------------------------------------------------------------------


def _store(project, notes, problems, updated_since, state):
    """Les notes, les illisibles et la nouvelle marque, ensemble : la marque n'avance que si la page est rangée."""
    with ballet_db.writing(state) as connection:
        for issue, note in notes:
            connection.execute(
                "INSERT INTO workshop_costs (project, session, segment, issue, title, started_at, ended_at, tokens, usd) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (project, session, segment) DO UPDATE SET issue = excluded.issue, "
                "title = excluded.title, started_at = excluded.started_at, ended_at = excluded.ended_at, "
                "tokens = excluded.tokens, usd = excluded.usd",
                (project, note["session"], note["segment"], issue["number"], issue.get("title", ""), note["from"], note["to"],
                 json.dumps(note["tokens"]), note["usd"]))
        for issue, comment, problem in problems:
            connection.execute("INSERT OR REPLACE INTO workshop_cost_problems (project, comment, issue, title, problem) "
                               "VALUES (?, ?, ?, ?, ?)", (project, comment, issue["number"], issue.get("title", ""), problem))
        connection.execute("INSERT OR REPLACE INTO workshop_cost_watermarks (project, updated_since) VALUES (?, ?)",
                           (project, updated_since))


def _sessions_of(rows):
    sessions = {}
    for row in rows:
        tokens = sum(sum(counts.values()) for counts in json.loads(row["tokens"]).values())
        into = sessions.setdefault((row["project"], row["session"]), {
            "project": row["project"], "session": row["session"], "issues": [], "usd": 0.0, "tokens": 0,
            "from": row["started_at"], "to": row["ended_at"]})
        into["issues"].append({"item": f"#{row['issue']}", "title": row["title"], "segment": row["segment"],
                               "usd": row["usd"], "tokens": tokens})
        into["usd"] = round(into["usd"] + row["usd"], 4)
        into["tokens"] += tokens
        into["from"], into["to"] = min(into["from"], row["started_at"]), max(into["to"], row["ended_at"])
    return [session | {"unknown": _unknown_segments(session)} for session in sessions.values()]


def _unknown_segments(session):
    seen = {issue["segment"] for issue in session["issues"]}
    return [f"segment {number}: cost unknown" for number in range(1, max(seen) + 1) if number not in seen]


# --- la ligne de commande -------------------------------------------------------------------------------------------


def main(argv):
    if len(argv) != 3 or argv[1] != "sweep":
        print("usage: ballet_workshop_costs.py sweep <project>", file=sys.stderr)
        return 2
    project = ballet_maestro.read_config()["projects"].get(argv[2])
    if not project:
        print(f"unknown project '{argv[2]}' in maestro.toml", file=sys.stderr)
        return 1
    try:
        print(sweep(argv[2], project["path"]))
    except WorkshopCostError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
