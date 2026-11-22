"""La Scène : une page locale, en lecture seule, de tout ce que Ballet joue sur la machine, lue dans `~/.ballet/ballet.db`.

    python3 ballet_stage.py                 # http://127.0.0.1:7700
    python3 ballet_stage.py --port 7710     # un autre port

La page (`stage/index.html`) a un Dashboard (la santé de Ballet, les indicateurs, l'activité), ce qui est en scène, le
programme, les Workshops, les Rehearsals, les tickets et les Premieres ; chaque représentation a ses transitions, sa
communication et son fil. Tous les projets de la machine, un sélecteur pour n'en garder qu'un.

Ce qui est lu, sans rien écrire : les nœuds et leurs événements, l'état des Rehearsals, Workshops et sessions, le registre
des Conductors, la file `ready` vue par le dernier tour du Monitor et la ligne `runtime` (la base) ; `maestro.toml`
(projets, limites, seuil de redémarrage) ; le profil de chaque projet (sa distribution) ; le transcript de Maestro (son
contexte) ; le remote git de chaque projet (les liens vers GitHub). Les titres des issues viennent de `gh`, lus en
arrière-plan puis gardés : la page s'ouvre tout de suite et les reçoit au tour suivant. Une issue que le Workshop a publiée
`proposed` y figure tant qu'elle n'est ni dans la file ni jouée : l'accepter se fait sur GitHub.

`/api/stage?since=<version>` répond `{"version", "unchanged": true}` quand rien n'a bougé. N'écoute que sur 127.0.0.1.
"""

import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import ballet_config
import ballet_conductors
import ballet_context
import ballet_db
import ballet_launch
import ballet_legacy
import ballet_maestro
import ballet_monitor
import ballet_runtime

STAGE = Path(__file__).resolve().parent.parent / "stage"
FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/vendor/mermaid.min.js": ("vendor/mermaid.min.js", "text/javascript"),
    "/vendor/fontawesome/css/all.min.css": ("vendor/fontawesome/css/all.min.css", "text/css"),
    "/vendor/fontawesome/webfonts/fa-solid-900.woff2": ("vendor/fontawesome/webfonts/fa-solid-900.woff2", "font/woff2"),
}
DEFAULT_PORT = 7700
LOCAL_HOSTS = {"127.0.0.1", "localhost"}
PLAYS = ("rehearsal", "workshop")
TEXT_LIMIT = 2000   # un message plus long est coupé : il est en entier sur GitHub
TITLES = {}   # (projet, issue) → titre ; une issue ne change pas de titre pendant qu'on la regarde
ASKED = set()   # les titres déjà demandés à gh
REPOS = {}   # projet → URL du repo sur GitHub, vide sans remote
CONTEXT = {}   # transcript → (mtime, tokens) : le transcript n'est relu que s'il a bougé
_LOCK = threading.Lock()
_TITLE_READERS = ThreadPoolExecutor(max_workers=6)


class UsageError(Exception):
    """La commande est mal formée : rien n'est lancé."""


def main(argv):
    try:
        port = _parsed(argv)
    except UsageError as error:
        print(f"ballet_stage: {error}", file=sys.stderr)
        return 2
    print(f"The curtain rises on http://127.0.0.1:{port}")
    _serve(port)
    return 0


def snapshot(since="", state=None):
    """Ce que la page affiche, en une fois ; `unchanged` quand rien n'a bougé depuis la version `since`."""
    with ballet_db.reading(state) as connection:
        version = _version(connection)
        if version == since:
            return {"version": version, "unchanged": True}
        config = ballet_maestro.read_config(state)
        plays, trees = _plays(connection)
        return {"version": version, "stage": {
            "now": _now(),
            "health": _health(connection, config, state),
            "projects": _projects(connection, config),
            "conductors": _conductors(connection),
            "plays": plays,
            "ready": _ready(connection),
            "proposed": _proposed(connection, plays),
        }, "plays": trees}


# --- les représentations --------------------------------------------------------


def _plays(connection):
    """Chaque Rehearsal et chaque Workshop joué, dans l'ordre où ils ont commencé, et l'arbre de chacun : ses nœuds avec
    leurs événements, et ses marques."""
    nodes = [dict(row) for row in connection.execute("SELECT * FROM nodes ORDER BY started_at")]
    events = _events_by_node(connection)
    context = _play_context(connection)
    plays, trees = [], {}
    for node in (node for node in nodes if node["kind"] in PLAYS):
        children = [{**child, "events": events.get(child["id"], [])} for child in nodes if child["parent"] == node["id"]]
        marks = events.get(node["id"], [])
        plays.append(_play(node, children, marks, context))
        trees[node["id"]] = {"marks": marks, "nodes": children}
    return plays, trees


def _play(node, children, marks, context):
    state = context["states"].get((node["kind"], node["project"], node["name"]), {})
    issue, key = str(state.get("issue") or ""), node["name"]
    session, legacy = _session_of(node, context)
    return {
        "node": node["id"], "project": node["project"], "kind": node["kind"], "key": key, "conductor": node["conductor"],
        "title": _title(node["project"], issue) or state.get("framed") or key,
        "issue": issue, "pr": str(state.get("pull_request") or ""),
        "planning": node["kind"] == "rehearsal" and bool(state.get("feature")) and not state.get("pull_request"),
        "started_at": node["started_at"], "ended_at": node["ended_at"], "outcome": node["outcome"],
        "status": state.get("status", ""), "counts": _counts(children, marks),
        "round_trips": state.get("round_trips", 0), "diff": (state.get("size") or {}).get("counted"),
        "published": next((mark["data"] for mark in marks if mark["kind"] == "published"), None), "simulated": False,
        "session": session, "legacy": legacy, "mode": _mode_of(node, context),
        "type": _type_of(node["kind"], key), "parent": key.split(".")[0] if "." in key else "",
    }


def _play_context(connection):
    """Ce dont chaque représentation a besoin autour d'elle : les états, les sessions et le registre des Conductors."""
    states = {("rehearsal", row["project"], row["id"]): json.loads(row["data"]) for row in connection.execute("SELECT * FROM rehearsals")}
    states |= {("workshop", row["project"], row["item"]): json.loads(row["data"]) for row in connection.execute("SELECT * FROM workshops")}
    sessions = {(row["project"], row["item"]): json.loads(row["data"]) for row in connection.execute("SELECT * FROM sessions")}
    registry = {row["id"] for row in connection.execute("SELECT id FROM conductors")}
    return {"states": states, "sessions": sessions, "registry": registry}


def _session_of(node, context):
    """La session de Conductor de la représentation. L'historique repris d'avant la base a un Conductor par Rehearsal,
    sans session ni ligne au registre : il est regroupé par feature, marqué `legacy`."""
    conductor = node["conductor"] or f"{node['project']}#{node['name']}"
    item = conductor.split("#", 1)[-1]
    if conductor in context["registry"] or _session_state(node["project"], item, context):
        return conductor, False
    return f"{node['project']}#{item.split('.')[0]}", True


def _mode_of(node, context):
    if node["kind"] == "workshop":
        return "autopilot"   # un Workshop qui a un Conductor est un Workshop autopilot
    item = (node["conductor"] or "").split("#", 1)[-1]
    return (_session_state(node["project"], item, context) or {}).get("mode") or "assisted"


def _session_state(project, item, context):
    return context["sessions"].get((project, item)) or context["sessions"].get((project, "#" + item))


def _type_of(kind, key):
    if kind == "workshop":
        return "Workshop"
    if "." in key:
        return "Slice"
    return {"FEAT": "Feature", "BUG": "Bug", "TASK": "Task"}.get(key.split("-")[0], "Feature")


def _counts(children, marks):
    count = lambda kind: sum(1 for child in children if child["kind"] == kind)
    messages = sum(1 for event in [*marks, *(event for child in children for event in child["events"])] if event["kind"] == "message")
    return {"turn": count("turn"), "proof": count("proof"), "mutation": count("mutation"), "director": count("director"), "message": messages}


def _events_by_node(connection):
    found = {}
    for row in connection.execute("SELECT * FROM events ORDER BY id"):
        found.setdefault(row["node"], []).append({"id": row["id"], "at": row["at"], "phase": row["phase"], "kind": row["kind"],
                                                  "actor": row["actor"], "data": _short(row["data"])})
    return found


def _short(data):
    """Les données d'un événement, ses longs textes coupés à `TEXT_LIMIT`."""
    found = json.loads(data or "{}")
    for key, value in found.items():
        if isinstance(value, str) and len(value) > TEXT_LIMIT:
            found[key] = value[:TEXT_LIMIT] + "…"
    return found


# --- la file, les issues proposées, les Conductors --------------------------------------


def _ready(connection):
    """La file de chaque projet telle que le dernier tour du Monitor l'a vue, dans l'ordre de jeu."""
    return [{"project": row["project"], "item": item["item"], "type": item.get("type", ""), "priority": item.get("priority", ""),
             "mode": item.get("mode", ""), "title": item.get("title", ""), "url": item.get("url", ""),
             "blocked_by": [blocker["item"] if isinstance(blocker, dict) else str(blocker) for blocker in item.get("blocked_by", [])]}
            for row in connection.execute("SELECT project, items FROM ready ORDER BY project") for item in json.loads(row["items"])]


def _proposed(connection, plays):
    """Les issues qu'un Workshop autopilot a publiées `proposed` et que rien n'a encore prises : ni la file, ni une session."""
    taken = {(item["project"], item["item"]) for item in _ready(connection)}
    taken |= {(row["project"], row["item"]) for row in connection.execute("SELECT project, item FROM sessions")}
    found = []
    for play in plays:
        published = play["published"] or {}
        key = (play["project"], f"#{published.get('issue')}")
        if published.get("status") == "proposed" and key not in taken:
            found.append({"project": play["project"], "item": key[1], "type": published.get("type", ""),
                          "title": _title(play["project"], str(published.get("issue"))) or published.get("item", ""),
                          "decided_alone": published.get("decided_alone", 0), "node": play["node"]})
    return found


def _conductors(connection):
    rows = connection.execute("SELECT c.*, n.started_at, n.ended_at, n.outcome FROM conductors c JOIN nodes n ON n.id = c.node")
    return [{key: row[key] for key in ("id", "project", "item", "kind", "state", "node", "started_at", "ended_at", "outcome")} for row in rows]


# --- les projets ------------------------------------------------------------------


def _projects(connection, config):
    """Les projets de `maestro.toml` et ceux que la base connaît, chacun avec sa distribution et son repo sur GitHub."""
    paths = {alias: Path(project["path"]) for alias, project in config["projects"].items()}
    known = {row["project"] for row in connection.execute("SELECT DISTINCT project FROM nodes WHERE project IS NOT NULL")}
    return [{"alias": alias, "cast": _cast(paths.get(alias)), "repo": _repo(alias, paths.get(alias))} for alias in sorted(set(paths) | known)]


def _cast(home):
    """Le CLI et le modèle de chaque rôle, d'après le profil du projet ; rien quand il est illisible."""
    if not home:
        return {}
    try:
        roles = ballet_config.effective_config(home).get("roles", {})
    except (ballet_config.ConfigError, OSError):
        return {}
    return {role: " ".join(filter(None, (spec.get("cli"), spec.get("model")))) for role, spec in roles.items()}


def _repo(alias, home):
    """L'URL du repo sur GitHub, d'après le remote `origin` du projet ; vide sans remote GitHub."""
    if alias not in REPOS:
        REPOS[alias] = _github_url(_git_remote(home)) if home else ""
    return REPOS[alias]


def _git_remote(home):
    try:
        done = subprocess.run(["git", "-C", str(home), "remote", "get-url", "origin"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def _github_url(remote):
    """`git@github.com:o/r.git` ou `https://github.com/o/r.git` → `https://github.com/o/r`."""
    if "github.com" not in remote:
        return ""
    path = remote.split("github.com", 1)[1].lstrip(":/")
    return "https://github.com/" + path.removesuffix(".git")


# --- les titres des issues ----------------------------------------------------------


def _title(project, issue):
    """Le titre de l'issue, sans son préfixe `FEAT-008 · ` ; vide tant que `gh` ne l'a pas donné (il est demandé une fois,
    en arrière-plan)."""
    if not issue:
        return ""
    key = (project, issue)
    with _LOCK:
        if key not in TITLES and key not in ASKED:
            ASKED.add(key)
            _TITLE_READERS.submit(_fetch_title, key)
        return TITLES.get(key, "").split(" · ", 1)[-1]


def _fetch_title(key):
    project, issue = key
    title = _read_title(_home_of(project), issue)
    with _LOCK:
        TITLES[key] = title


def _home_of(project):
    path = ballet_maestro.read_config()["projects"].get(project, {}).get("path")
    return Path(path) if path else None


def _read_title(home, issue):
    """Le titre de l'issue sur GitHub ; vide si `gh` n'est pas là ou ne répond pas : la page affiche la clé."""
    if not home:
        return ""
    try:
        done = subprocess.run(["gh", "issue", "view", issue, "--json", "title", "-q", ".title"],
                              cwd=home, capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


# --- la santé de Ballet ----------------------------------------------------------------


def _health(connection, config, state):
    runtime = ballet_runtime.read_in(connection)
    return {
        "maestro": _maestro(runtime, config),
        "mailbox": {"terminal": runtime["mailbox_terminal"], "run": runtime["mailbox_run"]},
        "monitor": {"terminal": runtime["monitor_terminal"], "interval_s": ballet_monitor.DEFAULT_INTERVAL,
                    "seen_at": connection.execute("SELECT max(seen_at) FROM ready").fetchone()[0]},
        "paused_at": runtime["paused_at"],
        "legacy_pending": bool(ballet_legacy.pending(state)),
        "db": _database(connection, state),
        "limits": _limits(connection, config, state),
    }


def _maestro(runtime, config):
    """Le bail de la session Maestro et son contexte, en pourcentage de sa fenêtre ; `None` quand il ne se lit pas."""
    try:
        restart_at, window = ballet_maestro.restart_percent(config), ballet_maestro.context_window(config)
    except ballet_maestro.MaestroError:
        restart_at, window = None, None
    used = _context_tokens(runtime["lease_session"])
    return {"terminal": runtime["maestro_terminal"], "lease_owner": runtime["lease_owner"], "lease_pid": runtime["lease_pid"],
            "lease_renewed_at": runtime["lease_renewed_at"], "session": runtime["lease_session"], "restart_at": restart_at,
            "context_percent": used * 100 // window if used is not None and window else None}


def _context_tokens(session):
    transcript = ballet_context.transcript_of(session) if session else None
    if not transcript:
        return None
    mtime = transcript.stat().st_mtime
    if CONTEXT.get(transcript, (None,))[0] != mtime:
        CONTEXT[transcript] = (mtime, ballet_context.used_tokens(transcript))
    return CONTEXT[transcript][1]


def _database(connection, state):
    path = ballet_db.database_path(state)
    return {"user_version": ballet_db.version(connection), "size_kb": path.stat().st_size // 1024 if path.exists() else 0,
            "events": connection.execute("SELECT count(*) FROM events").fetchone()[0]}


def _limits(connection, config, state):
    limit = lambda name: config.get("limits", {}).get(name, ballet_launch.DEFAULT_LIMITS[name])
    return {"max_running": limit("max_running"), "max_per_day": limit("max_per_day"),
            "launched_today": ballet_conductors.launches_today(state)}


# --- la version, l'heure ------------------------------------------------------------------


def _version(connection):
    """Une empreinte de ce qui est lu : le dernier événement, les états écrits, la file vue, les titres reçus."""
    stamps = [connection.execute("SELECT max(id) FROM events").fetchone()[0]]
    stamps += [tuple(connection.execute(f"SELECT max(updated_at), count(*) FROM {table}").fetchone()) for table in ("sessions", "rehearsals", "workshops")]
    stamps += [connection.execute("SELECT max(seen_at) FROM ready").fetchone()[0], tuple(ballet_runtime.read_in(connection).values())]
    with _LOCK:
        stamps.append(len(TITLES))
    return str(hash(json.dumps(stamps, default=str)))


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- ligne de commande, serveur --------------------------------------------------------


def _parsed(argv):
    rest, port = list(argv), DEFAULT_PORT
    while rest:
        argument = rest.pop(0)
        if argument != "--port":
            raise UsageError(f"unknown argument {argument} (the Stage reads every project of the machine's base; only --port is accepted)")
        port = _port(rest.pop(0) if rest else "")
    return port


def _port(text):
    if not text.isdigit() or not 0 < int(text) < 65536:
        raise UsageError(f"invalid port {text!r}")
    return int(text)


def _serve(port):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("The curtain falls.")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not _is_local(self.headers.get("Host", "")):
            return self._reply(403, "text/plain", b"forbidden")
        url = urlparse(self.path)
        if url.path in FILES:
            name, content_type = FILES[url.path]
            return self._reply(200, content_type, (STAGE / name).read_bytes())
        if url.path == "/api/stage":
            since = parse_qs(url.query).get("since", [""])[0]
            try:
                body = snapshot(since)
            except (*ballet_db.ERRORS, OSError) as error:
                return self._reply(503, "application/json", json.dumps({"error": str(error)}).encode())
            return self._reply(200, "application/json", json.dumps(body, ensure_ascii=False).encode())
        self._reply(404, "text/plain", b"not found")

    def _reply(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def _is_local(host_header):
    return host_header.rsplit(":", 1)[0] in LOCAL_HOSTS if ":" in host_header else host_header in LOCAL_HOSTS


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
