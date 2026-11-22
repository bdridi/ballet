"""Le registre des Conductors de Maestro (OPP-02) : `~/.ballet/conductors.json` (`BALLET_HOME` pour un autre dossier).

Une ligne par `<projet>#<élément>`, écrite par deux voies : `ballet_launch.py` quand Maestro lance le Conductor, et
`ballet_maestro.py` (`wait`, `recap`) quand un Conductor annonce `escalate` ou `done`. Chaque ligne :

    project, item   le projet (son alias) et l'élément (`12`, `FEAT-002`, `BUG-004`)
    kind            `rehearsal` ou `workshop` ; vide pour un Conductor que Maestro n'a pas lancé
    terminal        le terminal Orca du Conductor : c'est où `tell` écrit
    url             l'URL Remote Control de sa session ; vide quand on ne l'a pas trouvée
    started         la date du dernier lancement ; `starts`, celles des dernières 48 heures (le plafond du jour)
    seen, event     la date et le nom du dernier événement annoncé (`escalate`, `done`)
    state           `running` ; `finished` dès que le Conductor a annoncé `done` ; `gone` quand le Monitor a vu son
                    terminal disparaître d'Orca alors qu'il tournait encore ; `closed` quand Maestro a fermé le terminal
                    d'un Conductor fini (`ballet_launch.py close`) ; `stopped` quand Maestro l'a arrêté en cours de route
                    (`ballet_launch.py stop`) : terminal fermé, workers arrêtés, travail gardé
    finished_told   vrai quand le Monitor a signalé à Maestro ce Conductor fini dont le terminal restait ouvert

Une ligne écrite avant l'étape 3 (terminal, `seen`, `event`) reste lisible : ce qui manque se déduit.
Toute écriture passe par un verrou, un fichier temporaire, puis un renommage.
"""

import json
import re
from datetime import datetime, timedelta, timezone

import ballet_state

CONDUCTORS_NAME = "conductors.json"
RUNNING, FINISHED, GONE, CLOSED, STOPPED = "running", "finished", "gone", "closed", "stopped"
DONE_EVENT = "done"
CONDUCTOR_EVENTS = ("escalate", DONE_EVENT)   # ce que dit un Conductor ; `ready` et `gone` sont ceux du Monitor
CONDUCTOR_SUBJECT = re.compile(r"^(\S+#\S+) · (.+)$")   # `<projet>#<élément> · <événement>`
KEEP_STARTS = timedelta(hours=48)


def read(state=None):
    """Tout le registre : `<projet>#<élément>` → sa ligne ; vide sans fichier."""
    path = _path(state)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def record_launch(key, project, item, kind, terminal, state=None):
    """Une nouvelle ligne pour un lancement : elle remplace celle du même élément, dont elle garde les dates de lancement."""
    now = _now()
    with ballet_state.locked(state):
        registry = read(state)
        starts = [*_recent(registry.get(key, {}).get("starts", [])), now]
        registry[key] = {"project": project, "item": item, "kind": kind, "terminal": terminal, "url": "",
                         "started": now, "starts": starts, "seen": "", "event": "", "state": RUNNING}
        _write(registry, state)


def note_url(key, url, state=None):
    """L'URL Remote Control trouvée après le lancement, sur la ligne du lancement."""
    with ballet_state.locked(state):
        registry = read(state)
        if key in registry:
            registry[key]["url"] = url
            _write(registry, state)


def note_events(messages, state=None):
    """Chaque `status` de sujet `<projet>#<élément> · <événement>` dit où est son Conductor (son terminal expéditeur) et
    ce qu'il vient d'annoncer ; `done` clôt la ligne. Un Conductor que Maestro n'a pas lancé reçoit une ligne ici.
    Les messages du Monitor (`ready`, `gone`) ne disent rien d'un Conductor : ils sont ignorés."""
    seen = {}
    for message in messages:
        found = CONDUCTOR_SUBJECT.match(message.get("subject", ""))
        if message.get("type") == "status" and found and found.group(2) in CONDUCTOR_EVENTS and message.get("from"):
            seen[found.group(1)] = (message["from"], found.group(2))
    if not seen:
        return
    with ballet_state.locked(state):
        registry = read(state)
        for key, (terminal, event) in seen.items():
            registry[key] = _seen(registry.get(key) or _unlaunched(key), terminal, event)
        _write(registry, state)


def mark_gone(key, terminal, state=None):
    """Le Monitor ne retrouve plus le terminal d'un Conductor qui tournait : sa ligne passe à `gone`. Une ligne qui a
    changé entre-temps (finie, relancée dans un autre terminal) n'est pas touchée. Rend vrai quand elle a été marquée."""
    with ballet_state.locked(state):
        registry = read(state)
        line = registry.get(key)
        if not line or state_of(line) != RUNNING or line["terminal"] != terminal:
            return False
        registry[key] = {**line, "state": GONE, "seen": _now(), "event": GONE}
        _write(registry, state)
        return True


def finished_open(registry, delay_minutes, alive):
    """Les Conductors lancés par Maestro, finis depuis plus de `delay_minutes`, dont le terminal vit encore et que le
    Monitor n'a pas encore signalés : `<projet>#<élément>` → sa ligne."""
    limit = datetime.now(timezone.utc) - timedelta(minutes=delay_minutes)
    return {key: line for key, line in registry.items()
            if state_of(line) == FINISHED and line.get("kind") and not line.get("finished_told")
            and line.get("seen") and datetime.fromisoformat(line["seen"]) <= limit and line["terminal"] in alive}


def note_finished_told(key, terminal, state=None):
    """Le Monitor a signalé ce Conductor fini : il ne le refait pas. Une ligne qui a changé entre-temps n'est pas touchée."""
    with ballet_state.locked(state):
        registry = read(state)
        line = registry.get(key)
        if line and state_of(line) == FINISHED and line["terminal"] == terminal:
            registry[key] = {**line, "finished_told": True}
            _write(registry, state)


def mark_closed(key, terminal, state=None):
    """Maestro a fermé le terminal d'un Conductor fini : sa ligne passe à `closed`. Rend vrai quand elle a été marquée."""
    with ballet_state.locked(state):
        registry = read(state)
        line = registry.get(key)
        if not line or state_of(line) != FINISHED or line["terminal"] != terminal:
            return False
        registry[key] = {**line, "state": CLOSED, "seen": _now(), "event": CLOSED}
        _write(registry, state)
        return True


def mark_stopped(key, terminal, state=None):
    """Maestro a arrêté un Conductor qui tournait (ou dont le terminal avait disparu) : sa ligne passe à `stopped`. Une
    ligne qui a changé entre-temps n'est pas touchée. Rend vrai quand elle a été marquée."""
    with ballet_state.locked(state):
        registry = read(state)
        line = registry.get(key)
        if not line or state_of(line) not in (RUNNING, GONE) or line["terminal"] != terminal:
            return False
        registry[key] = {**line, "state": STOPPED, "seen": _now(), "event": STOPPED}
        _write(registry, state)
        return True


def state_of(line):
    """`running` ou `finished` ; une ligne d'avant l'état se lit sur son dernier événement."""
    return line.get("state") or (FINISHED if line.get("event") == DONE_EVENT else RUNNING)


def launches_today(registry):
    """Combien de Conductors ont été lancés aujourd'hui (jour local), toutes lignes confondues."""
    today = datetime.now().astimezone().date()
    return sum(1 for line in registry.values() for start in line.get("starts", []) if _local_day(start) == today)


def _seen(line, terminal, event):
    return {**line, "terminal": terminal, "seen": _now(), "event": event, "finished_told": False,
            "state": FINISHED if event == DONE_EVENT else RUNNING}


def _unlaunched(key):
    project, _, item = key.partition("#")
    return {"project": project, "item": item, "kind": "", "url": "", "started": "", "starts": []}


def _recent(starts):
    limit = datetime.now(timezone.utc) - KEEP_STARTS
    return [start for start in starts if datetime.fromisoformat(start) > limit]


def _local_day(start):
    return datetime.fromisoformat(start).astimezone().date()


def _write(registry, state):
    ballet_state.write_atomically(_path(state), json.dumps(registry, indent=2, ensure_ascii=False) + "\n")


def _path(state=None):
    return ballet_state.state_dir(state) / CONDUCTORS_NAME


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
