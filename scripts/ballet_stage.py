"""La Scène : sert la page `stage/index.html`, qui montre en direct et en archive ce qui se joue dans les projets.

    python3 ballet_stage.py [<home> ...]            # un ou plusieurs homes de projet
    python3 ballet_stage.py --scan <dossier>        # tous les sous-dossiers qui ont un `.ballet/run/`
    python3 ballet_stage.py --port 7700             # le port d'écoute (7700 par défaut)

La page d'origine répond sur `/`, la nouvelle (`stage/v2.html`) sur `/v2` : les deux lisent les mêmes données.

Lecture seule : le script lit `.ballet/run/` de chaque projet (états `<ID>.json` et `journal.jsonl`), le profil
(CLI et modèle par rôle, seuils d'escalade) et le titre des issues des Rehearsals (`gh issue view`, gardé en mémoire).
Le programme, ce qui attend sa Rehearsal, vient de GitHub (`ballet_program.py`, relu toutes les 30 secondes) ;
chaque session de Conductor ouverte (`session-<élément>.json`) fournit l'élément confié, son mode, ses slices qui
restent et sa Rehearsal courante ; l'historique vient du journal : chaque `begin` est une Rehearsal jouée. Si GitHub ne répond pas, la page le dit.
Il n'écoute que sur 127.0.0.1. Sans argument, le projet est le dossier courant.
"""

import json
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import ballet_config
import ballet_program

STAGE = Path(__file__).resolve().parent.parent / "stage"
PAGE = STAGE / "index.html"
PAGES = {"/": PAGE, "/index.html": PAGE, "/v2": STAGE / "v2.html", "/v2.html": STAGE / "v2.html"}
RUN_DIR = Path(".ballet") / "run"
SESSION_PREFIX = "session-"
PROGRAM_TTL_SECONDS = 30
LIMITS = ("max_round_trips", "max_diff_lines", "max_diff_strict", "max_exchange_rounds")
DEFAULT_PORT = 7700
LOCAL_HOSTS = {"127.0.0.1", "localhost"}
TITLES = {}   # (home, issue) → titre : une issue ne change pas de titre pendant qu'on la regarde
PROGRAMS = {}   # home → (heure de lecture, programme) : GitHub n'est pas interrogé à chaque tour de la page


class UsageError(Exception):
    """La commande est mal formée : rien n'est lancé."""


def main(argv):
    try:
        homes, port = _parsed(argv)
    except UsageError as error:
        print(f"ballet_stage: {error}", file=sys.stderr)
        return 2
    _announce(homes, port)
    _serve(homes, port)
    return 0


def snapshot(homes, since=""):
    """Ce que la page affiche : les projets, leurs Rehearsals et leur journal. `unchanged` si rien n'a bougé depuis `since`."""
    version = _version(homes)
    if version == since:
        return {"version": version, "unchanged": True}
    return {"version": version, "projects": [_project(home) for home in homes]}


def project_homes(folder):
    """Les sous-dossiers de `folder` qui ont un journal Ballet, dans l'ordre alphabétique."""
    return sorted(child for child in Path(folder).iterdir() if (child / RUN_DIR).is_dir())


# --- lecture des projets ------------------------------------------------------


def _project(home):
    run = Path(home) / RUN_DIR
    states, journal, program, profile = _states(run), _journal(run), _program(home), _profile(home)
    sessions, finished = _sessions(run), _finished_sessions(run)
    return {
        "name": Path(home).resolve().name,
        "home": str(Path(home).resolve()),
        "cast": profile.get("roles", {}),
        "limits": _limits(profile),
        "titles": _titles(home, states),
        "rehearsals": states,
        "queue": _queue(program, sessions, finished, states, journal),
        "queue_titles": {**{item["item"]: item["title"] for item in program["items"]}, **_session_titles(home, sessions)},
        "queue_error": program["error"],
        "journal": journal,
    }


def _profile(home):
    """Le profil effectif du projet ; rien s'il est illisible : la page fait sans."""
    try:
        return ballet_config.effective_config(home)
    except (ballet_config.ConfigError, OSError):
        return {}


def _limits(profile):
    escalation = profile.get("escalation", {})
    return {key: escalation[key] for key in LIMITS if key in escalation}


def _titles(home, states):
    issues = {state["id"]: str(state.get("issue", "")) for state in states}
    return {rehearsal: _issue_title(home, issue) for rehearsal, issue in issues.items() if issue}


def _queue(program, sessions, finished, states, journal):
    """Ce que la page affiche : les sessions de Conductor ouvertes, le programme de GitHub sans les éléments qu'une
    session a déjà pris, ce qui a déjà été joué, et les sessions finies avec leurs frictions."""
    taken = {item for session in sessions for item in session["items"] + [entry["item"] for entry in session["played"]]}
    return {
        "sessions": sessions,
        "program": [item for item in program["items"] if item["item"] not in taken],
        "played": _played(journal, states),
        "finished_sessions": finished,
    }


def _played(journal, states):
    """Chaque `begin` du journal : l'élément et la Rehearsal qui l'a joué (la slice, quand une planification l'a absorbée)."""
    played_by = {state["planned_by"]: state["id"] for state in states if state.get("planned_by")}
    return [{"item": entry.get("detail", {}).get("item", ""), "rehearsal": played_by.get(entry["rehearsal"], entry["rehearsal"])}
            for entry in journal if entry.get("event") == "begin"]


def _sessions(run):
    """Les sessions de Conductor ouvertes (`session-<élément>.json`), chacune avec son élément confié, son mode, ses
    slices à venir et sa Rehearsal courante. Une session finie, ou un fichier à moitié écrit, n'en est pas une."""
    found = (_json(path) for path in sorted(run.glob(f"{SESSION_PREFIX}*.json")))
    return [_session(saved) for saved in found if saved and saved.get("item") and saved.get("status", "open") == "open"]


def _finished_sessions(run):
    """Les sessions de Conductor finies, la plus récente d'abord (par la date de leur fichier), avec les frictions de
    chacune de leurs Rehearsals."""
    paths = sorted(run.glob(f"{SESSION_PREFIX}*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    found = (_json(path) for path in paths)
    return [_session(saved) for saved in found if saved and saved.get("item") and saved.get("status") == "done"]


def _session(saved):
    return {
        "item": saved["item"],
        "mode": saved.get("mode", ""),
        "current": saved.get("current", ""),
        "items": list(saved.get("items", [])),
        "played": list(saved.get("played", [])),
        "frictions": dict(saved.get("frictions", {})),
    }


def _session_titles(home, sessions):
    """Le titre des issues d'une session : l'élément confié et ses slices qui attendent (`#35`) ; une feature sans issue
    (`FEAT-003`) n'a pas encore de titre."""
    items = [item for session in sessions for item in [session["item"], *session["items"]] if item.startswith("#")]
    return {item: _issue_title(home, item[1:]) for item in items}


def _program(home):
    """Les éléments prêts sur GitHub, gardés `PROGRAM_TTL_SECONDS` ; `error` dit pourquoi on ne les connaît pas."""
    key = str(Path(home).resolve())
    read_at, program = PROGRAMS.get(key, (0, None))
    if program is None or time.monotonic() - read_at > PROGRAM_TTL_SECONDS:
        program = _read_program(home)
        PROGRAMS[key] = (time.monotonic(), program)
    return program


def _read_program(home):
    try:
        return {"items": ballet_program.ready_items(home), "error": ""}
    except ballet_program.ProgramError as error:
        return {"items": [], "error": str(error)}


def _issue_title(home, issue):
    key = (str(Path(home).resolve()), issue)
    if key not in TITLES:
        TITLES[key] = _read_title(home, issue)
    return TITLES[key]


def _read_title(home, issue):
    """Le titre de l'issue sur GitHub ; vide si `gh` n'est pas là ou ne répond pas : la page affiche l'ID."""
    try:
        done = subprocess.run(["gh", "issue", "view", issue, "--json", "title", "-q", ".title"],
                              cwd=home, capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def _states(run):
    states = (_json(path) for path in sorted(run.glob("*.json")))
    return [state for state in states if state and "id" in state]


def _journal(run):
    path = run / "journal.jsonl"
    if not path.is_file():
        return []
    entries = (_json(line) for line in path.read_text(encoding="utf-8").splitlines())
    return [entry for entry in entries if entry and "rehearsal" in entry]


def _json(text_or_path):
    """Un fichier à moitié écrit (le script écrit en même temps) vaut `None` : la page réessaie au prochain tour."""
    try:
        text = text_or_path.read_text(encoding="utf-8") if isinstance(text_or_path, Path) else text_or_path
        return json.loads(text)
    except (OSError, ValueError):
        return None


def _version(homes):
    """Une empreinte de ce qui est lu : elle change dès qu'un état, le journal ou le programme change."""
    stamps = []
    for home in homes:
        stamps.append(json.dumps(_program(home), sort_keys=True))
        for path in sorted((Path(home) / RUN_DIR).glob("*.json*")):
            stat = path.stat()
            stamps.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
    return str(hash(tuple(stamps)))


# --- ligne de commande --------------------------------------------------------


def _parsed(argv):
    homes, port, rest = [], DEFAULT_PORT, list(argv)
    while rest:
        argument = rest.pop(0)
        if argument == "--port":
            port = _port(_value(rest, "--port"))
        elif argument == "--scan":
            homes += _scanned(_value(rest, "--scan"))
        elif argument.startswith("-"):
            raise UsageError(f"unknown option {argument}")
        else:
            homes.append(Path(argument))
    return _checked(homes or [Path(".")]), port


def _value(rest, option):
    if not rest:
        raise UsageError(f"{option} needs a value")
    return rest.pop(0)


def _port(text):
    if not text.isdigit() or not 0 < int(text) < 65536:
        raise UsageError(f"invalid port {text!r}")
    return int(text)


def _scanned(folder):
    if not Path(folder).is_dir():
        raise UsageError(f"{folder} is not a folder")
    return project_homes(folder)


def _checked(homes):
    missing = [str(home) for home in homes if not (home / RUN_DIR).is_dir()]
    if missing or not homes:
        raise UsageError(f"no Ballet journal in {', '.join(missing) or 'the given folders'} (expected .ballet/run/)")
    return homes


def _announce(homes, port):
    print(f"The curtain rises on http://127.0.0.1:{port}  (new stage: /v2)  ({len(homes)} project(s): {', '.join(h.resolve().name for h in homes)})")


# --- serveur ------------------------------------------------------------------


def _serve(homes, port):
    server = ThreadingHTTPServer(("127.0.0.1", port), _handler_for(homes))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("The curtain falls.")


def _handler_for(homes):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if not _is_local(self.headers.get("Host", "")):
                return self._reply(403, "text/plain", b"forbidden")
            url = urlparse(self.path)
            if url.path in PAGES:
                return self._reply(200, "text/html; charset=utf-8", PAGES[url.path].read_bytes())
            if url.path == "/api/stage":
                since = parse_qs(url.query).get("since", [""])[0]
                return self._reply(200, "application/json", json.dumps(snapshot(homes, since)).encode())
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

    return Handler


def _is_local(host_header):
    return host_header.rsplit(":", 1)[0] in LOCAL_HOSTS if ":" in host_header else host_header in LOCAL_HOSTS


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
