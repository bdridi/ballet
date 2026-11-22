"""Le journal de Ballet (OPP-79) : les nœuds du workflow et leurs événements, dans la base (`ballet_db.py`).

Un nœud est une étape qui commence et finit : un Conductor, une Rehearsal, le tour d'un rôle, la preuve, la mutation,
l'attente du Director. Il est joué par un agent (`agent`), un script (`script`) ou le Director (`human`). Un nœud sans fin
est en cours.

Un événement a toujours la même forme : quand (`at`), sur quel nœud, sa phase (`start` : le nœud commence ; `end` : il
finit ; `mark` : il se passe quelque chose pendant), ce qui s'est passé (`kind` : `launch`, `escalate`, `done`,
`message`…), qui l'écrit (`actor`) et son détail (`data`, du JSON). Un échange entre rôles ou entre sessions est une
marque `message`, sur le nœud de qui l'envoie, avec `from`, `to`, `type`, `subject` dans son détail.

Les fonctions prennent la connexion d'une transaction ouverte (`ballet_db.writing`) : l'événement s'écrit avec ce qui
change dans l'état, ou pas du tout.
"""

import json
import uuid
from datetime import datetime, timezone

AGENT, SCRIPT, HUMAN = "agent", "script", "human"
OK, FAILED, ESCALATED, STOPPED, TIMEOUT = "ok", "failed", "escalated", "stopped", "timeout"


def start(connection, kind, name, runner, actor, event="", parent=None, project=None, conductor=None, data=None, at=None):
    """Un nœud commence : sa ligne, puis son événement `start` (`event` le nomme, sinon le genre du nœud). Rend son id.
    `at` : la date, quand elle n'est pas maintenant (un ancien journal repris)."""
    node, now = uuid.uuid4().hex, at or now_iso()
    connection.execute("INSERT INTO nodes (id, parent, project, conductor, kind, name, runner, started_at) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (node, parent, project, conductor, kind, name, runner, now))
    _event(connection, node, "start", event or kind, actor, data, now)
    return node


def end(connection, node, outcome, actor, event="", data=None, at=None):
    """Un nœud finit, avec son issue. Un nœud déjà fini ne change pas : rend faux."""
    now = at or now_iso()
    changed = connection.execute("UPDATE nodes SET ended_at = ?, outcome = ? WHERE id = ? AND ended_at IS NULL",
                                 (now, outcome, node)).rowcount
    if changed:
        _event(connection, node, "end", event or _kind_of(connection, node), actor, data, now)
    return bool(changed)


def mark(connection, node, kind, actor, data=None, at=None):
    """Il se passe quelque chose sur un nœud, sans le commencer ni le finir."""
    _event(connection, node, "mark", kind, actor, data, at or now_iso())


def is_open(connection, node):
    row = connection.execute("SELECT ended_at FROM nodes WHERE id = ?", (node,)).fetchone()
    return bool(row) and row["ended_at"] is None


def last_event(connection, node):
    """Le dernier événement du nœud (`at`, `kind`…) ; None sans événement."""
    return connection.execute("SELECT * FROM events WHERE node = ? ORDER BY id DESC LIMIT 1", (node,)).fetchone()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _event(connection, node, phase, kind, actor, data, at):
    connection.execute("INSERT INTO events (at, node, phase, kind, actor, data) VALUES (?, ?, ?, ?, ?, ?)",
                       (at, node, phase, kind, actor, json.dumps(data or {}, ensure_ascii=False)))


def _kind_of(connection, node):
    return connection.execute("SELECT kind FROM nodes WHERE id = ?", (node,)).fetchone()["kind"]
