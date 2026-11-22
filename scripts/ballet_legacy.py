"""L'état d'avant la base (OPP-79), repris une seule fois, par une commande à part (ce n'est pas une migration : les
migrations ne font que le schéma de la base).

    python3 ballet_legacy.py import [<home> ...]   # reprend ce qui reste de l'ancien état, puis le met de côté ; sans
                                                   # rien, ne fait rien. Les homes : ceux de projets hors de maestro.toml

`/ballet:setup` la lance. Tant qu'un ancien fichier d'état reste, les commandes de Maestro, du Monitor, des lancements et
du redémarrage refusent de tourner (`refuse_if_pending`) : elles liraient un état vide et agiraient à l'aveugle.

Ce qui est repris, du dossier d'état (`~/.ballet`, ou `BALLET_HOME`) :

    maestro.toml          ses tables d'état (`[mailbox]`, `[lease]`, `[monitor]`, `[restart]`, et `terminal` de `[maestro]`)
                          passent dans `runtime` ; le fichier est réécrit sans elles, la config reste (l'original est
                          gardé en `maestro.toml.imported`)
    auto_launch_paused    le drapeau de pause : `paused_at`
    monitor.json          la file vue de chaque projet (table `ready`) et `context_told` (`context_told_session`)
    conductors.json       le registre : une ligne par Conductor, et son nœud (lancement, dernier événement, fin)

et de chaque projet de `maestro.toml` (et de chaque home nommé), son `.ballet/run/` :

    session-*.json, workshop-*.json, <ID>.json   les états des sessions, des Workshops et des Rehearsals
    journal.jsonl         rejoué, à ses dates, par les règles du journal (`ballet_store.log_in`) : l'historique a ses nœuds
    le reste              les fichiers de travail (missions, résultats de mutation, logs) vont dans `~/.ballet/projects/<alias>/`

puis `.ballet/run/` devient `.ballet/run.imported`.

Tout est repris dans une seule transaction ; chaque fichier repris est renommé `<nom>.imported` une fois la transaction
validée. Relancer ne refait donc rien.
"""

import json
import sys
import tomllib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import ballet_db
import ballet_state
import ballet_store

STATE_TABLES = ("mailbox", "lease", "monitor", "restart")
SUFFIX = ".imported"
OUTCOMES = {"finished": "ok", "closed": "ok", "gone": "failed", "stopped": "stopped"}
LEGACY_FILES = ("auto_launch_paused", "monitor.json", "conductors.json")
RUN_DIR = Path(".ballet") / "run"
STATE_PREFIXES = {"session-": "session", "workshop-": "workshop"}   # les genres de `ballet_store`, pas encore lu à l'import
USAGE = "usage: import [<home> ...]"


class LegacyError(ballet_db.DatabaseError):
    """Un ancien état n'a pas été repris : rien ne tourne avant."""


@dataclass
class Taken:
    """Un fichier ou un dossier repris. `config` : ce qui doit rester dans le fichier (la config d'un `maestro.toml`) ;
    `work_dir` : où vont les fichiers de travail d'un `.ballet/run/`. Sinon, il est mis de côté entier."""
    path: Path
    config: dict | None = None
    work_dir: Path | None = None


def run_import(state=None, homes=()):
    """Reprend l'ancien état dans la base, d'un coup, puis met ses fichiers de côté. Rend ce qui a été repris."""
    folder = ballet_state.state_dir(state)
    projects = [(Path(home), ballet_store.project_of(home)) for home in _homes(folder, homes) if (Path(home) / RUN_DIR).is_dir()]
    with ballet_db.writing(state) as connection:
        taken = import_into(connection, folder)
        for home, project in projects:
            taken += _project_run(connection, home, project, folder)
    set_aside(taken)
    return [entry.path for entry in taken]


def pending(state=None, homes=()):
    """Les anciens fichiers d'état qui attendent leur reprise ; vide quand il n'y a rien."""
    folder = ballet_state.state_dir(state)
    found = [folder / name for name in LEGACY_FILES if (folder / name).is_file()]
    found += [folder / "maestro.toml"] if _holds_state(folder / "maestro.toml") else []
    return found + [Path(home) / RUN_DIR for home in _homes(folder, homes) if (Path(home) / RUN_DIR).is_dir()]


def refuse_if_pending(state=None, homes=()):
    """Lève tant qu'un ancien état n'a pas été repris (celui de la machine, ou d'un des projets)."""
    waiting = pending(state, homes)
    if waiting:
        raise LegacyError(f"the state of an older Ballet is not taken over yet ({', '.join(map(str, waiting))}): "
                          f"run python3 {Path(__file__).resolve()} import")


def old_runtime(state=None):
    """L'état de la machine encore dans un ancien `maestro.toml` (terminaux, bail), sous les noms de `ballet_runtime` ;
    vide quand il a été repris."""
    path = ballet_state.state_dir(state) / "maestro.toml"
    if not _holds_state(path):
        return {}
    return {name: value for name, value in _runtime_of(tomllib.loads(path.read_text(encoding="utf-8"))).items() if value}


def import_into(connection, folder):
    """Reprend ce qui existe dans `folder`, dans la transaction ouverte, sans toucher aux fichiers ; rend ce qui a été
    repris, à mettre de côté une fois la transaction validée."""
    folder = Path(folder)
    taken = []
    taken += _maestro_toml(connection, folder / "maestro.toml")
    taken += _pause_flag(connection, folder / "auto_launch_paused")
    taken += _monitor(connection, folder / "monitor.json")
    taken += _conductors(connection, folder / "conductors.json")
    return taken


def set_aside(taken):
    """Chaque fichier repris devient `<nom>.imported` ; celui qui garde de la config est copié ainsi, puis réécrit avec
    elle seule ; un `.ballet/run/` donne d'abord ses fichiers de travail au dossier de travail du projet."""
    for entry in taken:
        aside = entry.path.with_name(entry.path.name + SUFFIX)
        if entry.work_dir is not None:
            _move_work_files(entry.path, entry.work_dir)
        if entry.config is None:
            entry.path.replace(aside)
        else:
            aside.write_text(entry.path.read_text(encoding="utf-8"), encoding="utf-8")
            import ballet_maestro   # il importe la base : l'import se fait ici, pas en tête
            ballet_maestro.write_config(entry.config, entry.path.parent)


# --- les projets -----------------------------------------------------------------


def _homes(folder, named):
    """Les homes des projets de `maestro.toml`, puis ceux nommés, sans doublon."""
    path = folder / "maestro.toml"
    registered = tomllib.loads(path.read_text(encoding="utf-8")).get("projects", {}) if path.is_file() else {}
    homes = [Path(project["path"]) for project in registered.values() if project.get("path")] + [Path(home) for home in named]
    return list(dict.fromkeys(home.resolve() for home in homes))


def _project_run(connection, home, project, folder):
    """Les états d'un `.ballet/run/`, puis son journal rejoué à ses dates."""
    run = home / RUN_DIR
    sessions_of_rehearsals = {}
    for path in sorted(run.glob("*.json")):
        state = _json(path.read_text(encoding="utf-8"))
        what = _kind_of_state(path.name, state)
        if what:
            ballet_store.save_in(connection, project, what, state, _mtime(path))
            if what == ballet_store.REHEARSAL:
                sessions_of_rehearsals[state["id"]] = state.get("session", "")
    for entry in _journal_lines(run / "journal.jsonl"):
        scope = ballet_store.REHEARSAL if "rehearsal" in entry else ballet_store.WORKSHOP
        key = entry[scope]
        ballet_store.log_in(connection, project, scope, key, entry["event"], entry.get("detail", {}),
                            sessions_of_rehearsals.get(key, "") if scope == ballet_store.REHEARSAL else "", at=entry.get("at"))
    return [Taken(run, work_dir=folder / ballet_store.WORK_DIR / project)]


def _kind_of_state(name, state):
    """`session`, `workshop` ou `rehearsal` selon le fichier ; rien pour ce qui n'est pas un état (la file, un fichier abîmé)."""
    if not isinstance(state, dict):
        return None
    for prefix, what in STATE_PREFIXES.items():
        if name.startswith(prefix):
            return what if state.get("item") else None
    return ballet_store.REHEARSAL if state.get("id") else None


def _journal_lines(path):
    """Les entrées lisibles du journal, dans l'ordre ; une ligne abîmée (écrite à moitié) est sautée."""
    if not path.is_file():
        return []
    entries = (_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return [entry for entry in entries if isinstance(entry, dict) and entry.get("event") and ("rehearsal" in entry or "workshop" in entry)]


def _move_work_files(run, work_dir):
    """Ce qui n'est ni un état ni le journal (missions, résultats de mutation, logs) va au dossier de travail du projet."""
    work_dir.mkdir(parents=True, exist_ok=True)
    for path in run.iterdir():
        if path.name == "journal.jsonl" or (path.suffix == ".json" and path.is_file()):
            continue
        target = work_dir / path.name
        if not target.exists():
            path.replace(target)


def _json(text):
    try:
        return json.loads(text)
    except ValueError:
        return None


def _mtime(path):
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")


# --- maestro.toml -----------------------------------------------------------------


def _maestro_toml(connection, path):
    """L'état sort de `maestro.toml`, la config reste (le fichier est réécrit après la transaction)."""
    if not _holds_state(path):
        return []
    config = tomllib.loads(path.read_text(encoding="utf-8"))
    _update_runtime(connection, _runtime_of(config))
    return [Taken(path, _config_only(config))]


def _holds_state(path):
    if not path.is_file():
        return False
    config = tomllib.loads(path.read_text(encoding="utf-8"))
    return any(table in config for table in STATE_TABLES) or "terminal" in config.get("maestro", {})


def _runtime_of(config):
    mailbox, lease, restart = config.get("mailbox", {}), config.get("lease", {}), config.get("restart", {})
    return {
        "mailbox_terminal": mailbox.get("terminal"), "mailbox_run": mailbox.get("run"),
        "mailbox_previous_run": mailbox.get("previous_run"),
        "maestro_terminal": config.get("maestro", {}).get("terminal"),
        "monitor_terminal": config.get("monitor", {}).get("terminal"),
        "restart_terminal": restart.get("terminal"), "restart_owns_pause": int(bool(restart.get("paused"))),
        "lease_owner": lease.get("owner") or None, "lease_pid": lease.get("pid") or 0,
        "lease_renewed_at": lease.get("renewed") or None, "lease_session": lease.get("session") or None,
    }


def _config_only(config):
    kept = {key: value for key, value in config.items() if key not in STATE_TABLES}
    if "maestro" in kept:
        kept["maestro"] = {key: value for key, value in kept["maestro"].items() if key != "terminal"}
        if not kept["maestro"]:
            del kept["maestro"]
    return kept


# --- la pause ---------------------------------------------------------------------


def _pause_flag(connection, path):
    if not path.is_file():
        return []
    _update_runtime(connection, {"paused_at": path.read_text(encoding="utf-8").strip() or _now()})
    return [Taken(path)]


# --- monitor.json -----------------------------------------------------------------


def _monitor(connection, path):
    if not path.is_file():
        return []
    document = json.loads(path.read_text(encoding="utf-8"))
    for alias, project in document.get("projects", {}).items():
        connection.execute("INSERT OR REPLACE INTO ready (project, items, seen_at) VALUES (?, ?, ?)",
                           (alias, json.dumps(project.get("ready", []), ensure_ascii=False), _now()))
    told = document.get("maestro", {}).get("context_told")
    if told:
        _update_runtime(connection, {"context_told_session": told})
    return [Taken(path)]


# --- conductors.json --------------------------------------------------------------


def _conductors(connection, path):
    """Chaque ligne du registre, et son nœud : commencé à son lancement (ou à sa première annonce), son dernier
    événement à sa date, fini quand la ligne n'est plus `running`."""
    if not path.is_file():
        return []
    for key, line in json.loads(path.read_text(encoding="utf-8")).items():
        _conductor(connection, key, line)
    return [Taken(path)]


def _conductor(connection, key, line):
    project, _, item = key.partition("#")
    state = line.get("state") or ("finished" if line.get("event") == "done" else "running")
    started = line.get("started") or line.get("seen") or _now()
    seen = line.get("seen") or started
    node = uuid.uuid4().hex
    ended = seen if state != "running" else None
    connection.execute("INSERT INTO nodes (id, project, conductor, kind, name, runner, started_at, ended_at, outcome) "
                       "VALUES (?, ?, ?, 'conductor', ?, 'agent', ?, ?, ?)",
                       (node, project, key, key, started, ended, OUTCOMES.get(state)))
    _event(connection, started, node, "start", "launch" if line.get("kind") else "seen", "maestro", {"terminal": line.get("terminal")})
    if line.get("event"):
        _event(connection, seen, node, "end" if ended else "mark", line["event"], "conductor", {})
    connection.execute("INSERT OR REPLACE INTO conductors (id, project, item, kind, state, terminal, url, finished_told, node) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (key, line.get("project") or project, line.get("item") or item, line.get("kind") or None, state,
                        line.get("terminal"), line.get("url") or None, int(bool(line.get("finished_told"))), node))


# --- outils -----------------------------------------------------------------------


def _update_runtime(connection, values):
    values = {name: value for name, value in values.items() if value is not None}
    if values:
        connection.execute(f"UPDATE runtime SET {', '.join(f'{name} = ?' for name in values)} WHERE one = 1", list(values.values()))


def _event(connection, at, node, phase, kind, actor, data):
    connection.execute("INSERT INTO events (at, node, phase, kind, actor, data) VALUES (?, ?, ?, ?, ?, ?)",
                       (at, node, phase, kind, actor, json.dumps(data, ensure_ascii=False)))


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- ligne de commande ------------------------------------------------------------


def main(argv):
    """Affiche ce qui a été repris et sort avec 0 ; 1 si la reprise échoue (rien n'est repris), 2 sur un usage invalide."""
    if argv[1:2] != ["import"]:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        taken = run_import(homes=argv[2:])
    except (*ballet_db.ERRORS, OSError, tomllib.TOMLDecodeError, json.JSONDecodeError) as error:
        print(f"legacy: nothing taken over: {error}", file=sys.stderr)
        return 1
    print("\n".join(f"taken over: {path} (now {path.name}{SUFFIX})" for path in taken) or "nothing to take over")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
