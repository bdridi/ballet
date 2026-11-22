"""L'état des Rehearsals, des sessions de Conductor et des Workshops d'un projet, et leur journal, dans la base
(`ballet_db.py`, OPP-79, étape 2).

    python3 ballet_store.py drop session|rehearsal|workshop <clé>   # depuis le home du projet : l'état oublié, le journal gardé

`drop` remplace l'ancien « supprimer son fichier de `.ballet/run/` » : abandonner une session (`drop session '#12'`) ou
un Workshop, sur le mot du Director.

Un projet s'y nomme par son alias (`maestro.toml`), sinon par le nom de son dossier. Chaque état y est gardé entier (le
JSON de sa dataclass) ; ses fichiers de travail (missions des workers, résultats de la mutation, messages à publier) vont
dans `~/.ballet/projects/<alias>/` (`work_dir`) : plus rien n'est écrit dans le projet.

Le journal est celui de la machine (`ballet_journal.py`) : des nœuds et leurs événements. `log` y écrit chaque événement
d'une Rehearsal ou d'un Workshop, une ligne par appel, nommée comme avant (`begin`, `handoff`, `message`, `proof-end`…,
son détail en `data`), et la range sur le bon nœud :

    rehearsal, workshop   le nœud de la boucle (un script) : `begin` le commence, `done` le finit (`ok`), comme `handover`
                          (une planification qui passe la main à sa première slice) et `stopped` (`stopped`) ; son parent est le nœud du Conductor qui la joue, quand le registre le connaît
    turn                  le tour d'un rôle (un agent) : le premier `handoff` vers lui le commence, son message (`report`,
                          `verdict`, `answer`, `question`, `escalation`) le finit
    director              l'attente du Director (un humain) : `escalate` la commence, l'événement suivant la finit
    proof, mutation       la preuve et chaque outil de mutation (des scripts) : `proof-start` / `proof-end`,
                          `mutation-start` / `mutation-end`

Les autres événements sont des marques sur le nœud de la boucle. Fermer un nœud sans événement à soi (l'attente du
Director qui finit, un tour encore ouvert à la fin) ajoute un événement du nom de son genre (`director`, `turn`) :
`journal_of` ne les rend pas, il rend le journal tel que les scripts l'ont écrit.
"""

import json
import sys
from datetime import datetime, timezone

import ballet_db
import ballet_journal
import ballet_maestro
import ballet_state

REHEARSAL, WORKSHOP = "rehearsal", "workshop"
WORK_DIR = "projects"
ENDING_MESSAGES = {"report": ballet_journal.OK, "verdict": ballet_journal.OK, "answer": ballet_journal.OK,
                   "question": ballet_journal.OK, "escalation": ballet_journal.ESCALATED}
KEEPS_THE_DIRECTOR = ("escalate", "frictions", "done", "handover", "stopped")
TABLES = {"session": ("sessions", "item"), REHEARSAL: ("rehearsals", "id"), WORKSHOP: ("workshops", "item")}


def project_of(home):
    """L'alias du projet dont `home` est le dossier (`maestro.toml`), sinon le nom du dossier."""
    return ballet_maestro.project_of(home, ballet_maestro.read_config())


def work_dir(home):
    """Le dossier de travail du projet : `~/.ballet/projects/<alias>/`, créé au besoin."""
    folder = ballet_state.state_dir() / WORK_DIR / project_of(home)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


# --- les états ------------------------------------------------------------------


def save(home, what, state):
    """Écrit l'état entier d'une session (`session`), d'une Rehearsal ou d'un Workshop, à la place de l'ancien."""
    project = project_of(home)
    with ballet_db.writing() as connection:
        save_in(connection, project, what, state)


def save_in(connection, project, what, state, updated_at=None):
    """Comme `save`, dans une transaction ouverte ; `updated_at` : la date d'un ancien état repris."""
    table, key = TABLES[what]
    columns = {"project": project, key: state[key], "status": state.get("status", "open"),
               "data": json.dumps(state, ensure_ascii=False), "updated_at": updated_at or _now(),
               **({"session": state.get("session") or None} if what == REHEARSAL else {})}
    names = ", ".join(columns)
    connection.execute(f"INSERT OR REPLACE INTO {table} ({names}) VALUES ({', '.join('?' for _ in columns)})",
                       list(columns.values()))


def load(home, what, key):
    """L'état d'une session, d'une Rehearsal ou d'un Workshop ; None quand il n'existe pas."""
    table, column = TABLES[what]
    with ballet_db.reading() as connection:
        row = connection.execute(f"SELECT data FROM {table} WHERE project = ? AND {column} = ?", (project_of(home), key)).fetchone()
    return json.loads(row["data"]) if row else None


def drop(home, what, key):
    """Oublie l'état d'une session, d'une Rehearsal ou d'un Workshop ; son journal reste. Rend vrai s'il existait."""
    table, column = TABLES[what]
    project = project_of(home)
    with ballet_db.writing() as connection:
        return bool(connection.execute(f"DELETE FROM {table} WHERE project = ? AND {column} = ?", (project, key)).rowcount)


def all_of(home, what, newest_first=False):
    """Tous les états d'un genre dans le projet : par clé, ou le plus récemment écrit d'abord."""
    table, column = TABLES[what]
    order = "updated_at DESC, rowid DESC" if newest_first else column
    with ballet_db.reading() as connection:
        rows = connection.execute(f"SELECT data FROM {table} WHERE project = ? ORDER BY {order}", (project_of(home),)).fetchall()
    return [json.loads(row["data"]) for row in rows]


def known(home):
    """Le projet a-t-il quelque chose dans la base : une session, une Rehearsal ou un Workshop ?"""
    project = project_of(home)
    with ballet_db.reading() as connection:
        return any(connection.execute(f"SELECT 1 FROM {table} WHERE project = ? LIMIT 1", (project,)).fetchone()
                   for table, _ in TABLES.values())


def version(home):
    """Une empreinte de l'état du projet : elle change dès qu'un état ou le journal change."""
    project = project_of(home)
    with ballet_db.reading() as connection:
        events = connection.execute("SELECT max(id) FROM events").fetchone()[0]
        written = [connection.execute(f"SELECT max(updated_at), count(*) FROM {table} WHERE project = ?", (project,)).fetchone()
                   for table, _ in TABLES.values()]
    return json.dumps([events, [tuple(row) for row in written]])


# --- le journal -----------------------------------------------------------------


def log(home, scope, key, event, detail, conductor=""):
    """Un événement d'une Rehearsal ou d'un Workshop (`scope`), rangé sur son nœud. `conductor` : l'élément de sa
    session (`#12`), pour le rattacher au nœud de son Conductor."""
    project = project_of(home)
    with ballet_db.writing() as connection:
        log_in(connection, project, scope, key, event, detail, conductor)


def log_in(connection, project, scope, key, event, detail, conductor="", at=None):
    """Comme `log`, dans une transaction ouverte ; `at` : la date d'un ancien événement repris."""
    play = _latest_play(connection, project, scope, key)
    if event == "begin" and (play is None or play["ended_at"]):
        _begin(connection, project, scope, key, conductor or key, detail, at)
        return
    node = play["id"] if play else _start_unseen(connection, project, scope, key, conductor or key, at)
    if event not in KEEPS_THE_DIRECTOR:
        _close_child(connection, node, "director", ballet_journal.OK, "director", at)
    RECORDERS.get(event, _mark)(connection, node, event, detail, at)


def journal_of(home, scope, key):
    """Les événements d'une Rehearsal ou d'un Workshop, dans l'ordre, tels que les scripts les ont écrits :
    `{at, <scope>: key, event, detail}`."""
    return [entry for entry in journal(home, scope) if entry[scope] == key]


def journal(home, scope):
    """Les événements de toutes les Rehearsals (ou tous les Workshops) du projet, dans l'ordre."""
    with ballet_db.reading() as connection:
        rows = connection.execute(
            """SELECT e.at, e.kind, e.data, coalesce(parent.name, n.name) AS play
               FROM events e JOIN nodes n ON n.id = e.node
               LEFT JOIN nodes parent ON parent.id = n.parent AND parent.kind = :scope
               WHERE n.project = :project AND (n.kind = :scope OR parent.id IS NOT NULL) AND e.kind != n.kind
               ORDER BY e.id""", {"scope": scope, "project": project_of(home)}).fetchall()
    return [{"at": row["at"], scope: row["play"], "event": row["kind"], "detail": json.loads(row["data"])} for row in rows]


# --- les nœuds de la boucle --------------------------------------------------------


def _latest_play(connection, project, scope, key):
    return connection.execute("SELECT id, ended_at, conductor FROM nodes WHERE project = ? AND kind = ? AND name = ? "
                              "ORDER BY started_at DESC, rowid DESC LIMIT 1", (project, scope, key)).fetchone()


def _begin(connection, project, scope, key, session_item, detail, at):
    conductor = f"{project}#{session_item.lstrip('#')}"
    ballet_journal.start(connection, scope, key, ballet_journal.SCRIPT, "conductor", event="begin",
                         parent=_conductor_node(connection, conductor), project=project, conductor=conductor, data=detail, at=at)


def _start_unseen(connection, project, scope, key, session_item, at):
    """Une boucle dont le début n'est pas dans la base (reprise d'un ancien état) : son nœud commence ici, sans événement à soi."""
    conductor = f"{project}#{session_item.lstrip('#')}"
    return ballet_journal.start(connection, scope, key, ballet_journal.SCRIPT, "conductor",
                                parent=_conductor_node(connection, conductor), project=project, conductor=conductor, at=at)


def _conductor_node(connection, conductor):
    """Le nœud du Conductor qui joue cet élément, s'il tourne encore ; None sinon."""
    row = connection.execute("SELECT c.node FROM conductors c JOIN nodes n ON n.id = c.node "
                             "WHERE c.id = ? AND n.ended_at IS NULL", (conductor,)).fetchone()
    return row["node"] if row else None


# --- chaque événement sur son nœud -----------------------------------------------------


def _mark(connection, node, event, detail, at=None):
    ballet_journal.mark(connection, node, event, "conductor", detail, at)


def _handoff(connection, node, event, detail, at=None):
    """Ce que le Conductor remet à un rôle : son tour commence, sauf s'il est déjà ouvert ou que c'est un rappel."""
    turn = _open_child(connection, node, "turn", detail.get("role", ""))
    if turn or detail.get("how") == "nudge":
        ballet_journal.mark(connection, turn or node, event, "conductor", detail, at)
    else:
        _start_child(connection, node, "turn", detail.get("role", ""), ballet_journal.AGENT, event, detail, at)


def _nudge(connection, node, event, detail, at=None):
    ballet_journal.mark(connection, _open_child(connection, node, "turn", detail.get("role", "")) or node, event, "conductor", detail, at)


def _message(connection, node, event, detail, at=None):
    """Un message reçu : sur le tour de qui l'envoie, qu'il finit quand c'est son rapport, son verdict, sa réponse ou sa question."""
    sender = detail.get("from", "")
    turn = _open_child(connection, node, "turn", sender)
    outcome = ENDING_MESSAGES.get(detail.get("type", ""))
    if turn and outcome:
        ballet_journal.end(connection, turn, outcome, sender, event=event, data=detail, at=at)
    else:
        ballet_journal.mark(connection, turn or node, event, sender or "conductor", detail, at)


def _escalate(connection, node, event, detail, at=None):
    """Une escalade : l'attente du Director commence (ou continue, si elle était déjà ouverte)."""
    waiting = _open_child(connection, node, "director", "director")
    if waiting:
        ballet_journal.mark(connection, waiting, event, "conductor", detail, at)
    else:
        _start_child(connection, node, "director", "director", ballet_journal.HUMAN, event, detail, at)


def _proof_start(connection, node, event, detail, at=None):
    _start_child(connection, node, "proof", detail.get("command", "proof"), ballet_journal.SCRIPT, event, detail, at)


def _proof_end(connection, node, event, detail, at=None):
    _end_child(connection, node, "proof", None, _outcome_of_run(detail), event, detail, at)


def _mutation_start(connection, node, event, detail, at=None):
    _start_child(connection, node, "mutation", detail.get("tool", "mutation"), ballet_journal.SCRIPT, event, detail, at)


def _mutation_end(connection, node, event, detail, at=None):
    _end_child(connection, node, "mutation", detail.get("tool", "mutation"), _outcome_of_run(detail), event, detail, at)


def _done(connection, node, event, detail, at=None):
    _close_children(connection, node, ballet_journal.OK, at)
    ballet_journal.end(connection, node, ballet_journal.OK, "conductor", event=event, data=detail, at=at)


def _stopped(connection, node, event, detail, at=None):
    _close_children(connection, node, ballet_journal.STOPPED, at)
    if not ballet_journal.end(connection, node, ballet_journal.STOPPED, "maestro", event=event, data=detail, at=at):
        ballet_journal.mark(connection, node, event, "maestro", detail, at)


RECORDERS = {"handoff": _handoff, "nudge": _nudge, "message": _message, "escalate": _escalate,
             "proof-start": _proof_start, "proof-end": _proof_end, "mutation-start": _mutation_start,
             "mutation-end": _mutation_end, "done": _done, "handover": _done, "stopped": _stopped}


# --- les nœuds enfants ---------------------------------------------------------------


def _start_child(connection, node, kind, name, runner, event, detail, at):
    parent = connection.execute("SELECT project, conductor FROM nodes WHERE id = ?", (node,)).fetchone()
    ballet_journal.start(connection, kind, name, runner, "conductor", event=event, parent=node, project=parent["project"],
                         conductor=parent["conductor"], data=detail, at=at)


def _end_child(connection, node, kind, name, outcome, event, detail, at):
    """Finit l'enfant ouvert de ce genre (et de ce nom, s'il est donné) ; sans enfant ouvert, l'événement est une marque."""
    child = _open_child(connection, node, kind, name)
    if not child or not ballet_journal.end(connection, child, outcome, "conductor", event=event, data=detail, at=at):
        _mark(connection, node, event, detail, at)


def _open_child(connection, node, kind, name=None):
    query = "SELECT id FROM nodes WHERE parent = ? AND kind = ? AND ended_at IS NULL"
    arguments = [node, kind]
    if name is not None:
        query, arguments = query + " AND name = ?", [*arguments, name]
    row = connection.execute(query + " ORDER BY started_at DESC, rowid DESC LIMIT 1", arguments).fetchone()
    return row["id"] if row else None


def _close_child(connection, node, kind, outcome, actor, at):
    child = _open_child(connection, node, kind)
    if child:
        ballet_journal.end(connection, child, outcome, actor, at=at)


def _close_children(connection, node, outcome, at):
    for row in connection.execute("SELECT id FROM nodes WHERE parent = ? AND ended_at IS NULL", (node,)).fetchall():
        ballet_journal.end(connection, row["id"], outcome, "conductor", at=at)


def _outcome_of_run(detail):
    if detail.get("timed_out"):
        return ballet_journal.TIMEOUT
    return ballet_journal.OK if detail.get("passed") else ballet_journal.FAILED


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- ligne de commande ------------------------------------------------------------


def main(argv, home="."):
    """`drop <genre> <clé>` : sort avec 0 quand l'état a été oublié, 1 s'il n'existait pas, 2 sur un usage invalide."""
    if len(argv) != 4 or argv[1] != "drop" or argv[2] not in TABLES:
        print("usage: drop session|rehearsal|workshop <key>   (from the project's home; a session's key is '#12' or FEAT-002)",
              file=sys.stderr)
        return 2
    if not drop(home, argv[2], argv[3]):
        print(f"no {argv[2]} {argv[3]} in project {project_of(home)}", file=sys.stderr)
        return 1
    print(f"{argv[2]} {argv[3]} of project {project_of(home)} dropped (its journal stays)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
