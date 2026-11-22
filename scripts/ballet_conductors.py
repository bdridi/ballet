"""Le registre des Conductors de Maestro (OPP-02) : la table `conductors` de la base (`ballet_db.py`, OPP-79).

Une ligne par `<projet>#<élément>`, celle de son dernier Conductor, écrite par deux voies : `ballet_launch.py` quand
Maestro lance le Conductor, et `ballet_maestro.py` (`wait`, `recap`) quand un Conductor annonce `escalate` ou `done`.
`read` rend chaque ligne ainsi :

    project, item   le projet (son alias) et l'élément (`12`, `FEAT-002`, `BUG-004`)
    kind            `rehearsal` ou `workshop` ; vide pour un Conductor que Maestro n'a pas lancé
    terminal        le terminal Orca du Conductor : c'est où `tell` écrit
    url             l'URL Remote Control de sa session ; vide quand on ne l'a pas trouvée
    started         la date du début de son nœud (son lancement, ou sa première annonce)
    seen, event     la date et le nom du dernier événement de son nœud (`escalate`, `done`, `gone`…) ; vides juste après
                    le lancement
    state           `running` ; `finished` dès que le Conductor a annoncé `done` ; `gone` quand le Monitor a vu son
                    terminal disparaître d'Orca alors qu'il tournait encore ; `closed` quand Maestro a fermé le terminal
                    d'un Conductor fini (`ballet_launch.py close`) ; `stopped` quand Maestro l'a arrêté en cours de route
                    (`ballet_launch.py stop`) : terminal fermé, workers arrêtés, travail gardé
    finished_told   vrai quand le Monitor a signalé à Maestro ce Conductor fini dont le terminal restait ouvert

Chaque Conductor est un nœud du journal (`ballet_journal.py`, genre `conductor`, joué par un agent) : son lancement le
commence (`launch`), ses annonces y sont des marques (`escalate`), `done` le finit (`ok`), comme `gone` (`failed`) et
`stop` (`stopped`). Un Conductor qui parle alors que son nœud est fini tourne de nouveau : un nouveau nœud commence
(`seen`). Les lancements du jour se comptent sur les événements `launch`.
"""

import re
from datetime import datetime, timedelta, timezone

import ballet_db
import ballet_journal

RUNNING, FINISHED, GONE, CLOSED, STOPPED = "running", "finished", "gone", "closed", "stopped"
DONE_EVENT = "done"
LAUNCH_EVENT = "launch"
CONDUCTOR_EVENTS = ("escalate", DONE_EVENT)   # ce que dit un Conductor ; `ready` et `gone` sont ceux du Monitor
CONDUCTOR_SUBJECT = re.compile(r"^(\S+#\S+) · (.+)$")   # `<projet>#<élément> · <événement>`
LINES = """SELECT c.*, n.started_at, e.at AS seen, e.kind AS event, e.phase
           FROM conductors c JOIN nodes n ON n.id = c.node
           LEFT JOIN events e ON e.id = (SELECT max(id) FROM events WHERE node = c.node)"""


def read(state=None):
    """Tout le registre : `<projet>#<élément>` → sa ligne ; vide sans Conductor."""
    with ballet_db.reading(state) as connection:
        return {row["id"]: _line(row) for row in connection.execute(f"{LINES} ORDER BY c.id")}


def record_launch(key, project, item, kind, terminal, state=None):
    """Un nouveau Conductor lancé : un nouveau nœud, et sa ligne remplace celle du même élément. Le nœud d'avant, s'il
    n'avait pas fini, est clos (`stopped`) : on ne le verra plus tourner."""
    with ballet_db.writing(state) as connection:
        previous = _row(connection, key)
        if previous:
            ballet_journal.end(connection, previous["node"], ballet_journal.STOPPED, "maestro", event="replaced")
        node = _start(connection, key, project, "maestro", LAUNCH_EVENT, {"kind": kind, "terminal": terminal})
        connection.execute("INSERT OR REPLACE INTO conductors (id, project, item, kind, state, terminal, node) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?)", (key, project, item, kind, RUNNING, terminal, node))


def note_url(key, url, state=None):
    """L'URL Remote Control trouvée après le lancement, sur la ligne du lancement."""
    with ballet_db.writing(state) as connection:
        connection.execute("UPDATE conductors SET url = ? WHERE id = ?", (url, key))


def note_events(messages, state=None):
    """Chaque `status` de sujet `<projet>#<élément> · <événement>` dit où est son Conductor (son terminal expéditeur) et
    ce qu'il vient d'annoncer ; `done` finit son nœud. Un Conductor que Maestro n'a pas lancé reçoit une ligne ici.
    Les messages du Monitor (`ready`, `gone`) ne disent rien d'un Conductor : ils sont ignorés."""
    seen = {}
    for message in messages:
        found = CONDUCTOR_SUBJECT.match(message.get("subject", ""))
        if message.get("type") == "status" and found and found.group(2) in CONDUCTOR_EVENTS and message.get("from"):
            seen[found.group(1)] = (message["from"], found.group(2))
    if not seen:
        return
    with ballet_db.writing(state) as connection:
        for key, (terminal, event) in seen.items():
            _note(connection, key, terminal, event)


def mark_gone(key, terminal, state=None):
    """Le Monitor ne retrouve plus le terminal d'un Conductor qui tournait : sa ligne passe à `gone`, son nœud finit. Une
    ligne qui a changé entre-temps (finie, relancée dans un autre terminal) n'est pas touchée. Rend vrai quand elle a été marquée."""
    with ballet_db.writing(state) as connection:
        row = _row(connection, key)
        if not row or row["state"] != RUNNING or row["terminal"] != terminal:
            return False
        _finish(connection, row, GONE, ballet_journal.FAILED, "monitor")
        return True


def finished_open(registry, delay_minutes, alive):
    """Les Conductors lancés par Maestro, finis depuis plus de `delay_minutes`, dont le terminal vit encore et que le
    Monitor n'a pas encore signalés : `<projet>#<élément>` → sa ligne."""
    limit = datetime.now(timezone.utc) - timedelta(minutes=delay_minutes)
    return {key: line for key, line in registry.items()
            if line["state"] == FINISHED and line["kind"] and not line["finished_told"]
            and line["seen"] and datetime.fromisoformat(line["seen"]) <= limit and line["terminal"] in alive}


def note_finished_told(key, terminal, state=None):
    """Le Monitor a signalé ce Conductor fini : il ne le refait pas. Une ligne qui a changé entre-temps n'est pas touchée."""
    with ballet_db.writing(state) as connection:
        connection.execute("UPDATE conductors SET finished_told = 1 WHERE id = ? AND state = ? AND terminal = ?",
                           (key, FINISHED, terminal))


def mark_closed(key, terminal, state=None):
    """Maestro a fermé le terminal d'un Conductor fini : sa ligne passe à `closed`. Rend vrai quand elle a été marquée."""
    with ballet_db.writing(state) as connection:
        row = _row(connection, key)
        if not row or row["state"] != FINISHED or row["terminal"] != terminal:
            return False
        _finish(connection, row, CLOSED, ballet_journal.OK, "maestro")
        return True


def mark_stopped(key, terminal, state=None):
    """Maestro a arrêté un Conductor qui tournait (ou dont le terminal avait disparu) : sa ligne passe à `stopped`. Une
    ligne qui a changé entre-temps n'est pas touchée. Rend vrai quand elle a été marquée."""
    with ballet_db.writing(state) as connection:
        row = _row(connection, key)
        if not row or row["state"] not in (RUNNING, GONE) or row["terminal"] != terminal:
            return False
        _finish(connection, row, STOPPED, ballet_journal.STOPPED, "maestro")
        return True


def state_of(line):
    return line["state"]


def launches_today(state=None):
    """Combien de Conductors ont été lancés aujourd'hui (jour local), tous éléments confondus."""
    today = datetime.now().astimezone().date()
    since = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(timespec="seconds")
    with ballet_db.reading(state) as connection:
        launches = connection.execute("SELECT at FROM events WHERE kind = ? AND at >= ?", (LAUNCH_EVENT, since)).fetchall()
    return sum(1 for launch in launches if datetime.fromisoformat(launch["at"]).astimezone().date() == today)


# --- les écritures ----------------------------------------------------------------


def _note(connection, key, terminal, event):
    """Une annonce : sur le nœud du Conductor s'il tourne, sinon sur un nouveau ; `done` le finit."""
    row = _row(connection, key)
    node = row["node"] if row and ballet_journal.is_open(connection, row["node"]) else None
    if node is None:
        node = _start(connection, key, key.partition("#")[0], "conductor", "seen", {"terminal": terminal})
    if event == DONE_EVENT:
        ballet_journal.end(connection, node, ballet_journal.OK, "conductor", event=DONE_EVENT, data={"terminal": terminal})
    else:
        ballet_journal.mark(connection, node, event, "conductor", {"terminal": terminal})
    project, _, item = key.partition("#")
    connection.execute(
        "INSERT INTO conductors (id, project, item, state, terminal, node) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (id) DO UPDATE SET state = excluded.state, terminal = excluded.terminal, node = excluded.node, finished_told = 0",
        (key, project, item, FINISHED if event == DONE_EVENT else RUNNING, terminal, node))


def _finish(connection, row, state, outcome, actor):
    """La ligne passe à `state` ; son nœud finit avec cette issue, ou reçoit la marque s'il avait déjà fini."""
    if not ballet_journal.end(connection, row["node"], outcome, actor, event=state):
        ballet_journal.mark(connection, row["node"], state, actor)
    connection.execute("UPDATE conductors SET state = ? WHERE id = ?", (state, row["id"]))


def _start(connection, key, project, actor, event, data):
    return ballet_journal.start(connection, "conductor", key, ballet_journal.AGENT, actor, event=event,
                                project=project, conductor=key, data=data)


def _row(connection, key):
    return connection.execute("SELECT * FROM conductors WHERE id = ?", (key,)).fetchone()


def _line(row):
    launched = row["phase"] == "start" and row["event"] == LAUNCH_EVENT
    return {"project": row["project"], "item": row["item"], "kind": row["kind"] or "", "terminal": row["terminal"] or "",
            "url": row["url"] or "", "started": row["started_at"], "seen": "" if launched else row["seen"],
            "event": "" if launched else row["event"], "state": row["state"], "finished_told": bool(row["finished_told"])}
