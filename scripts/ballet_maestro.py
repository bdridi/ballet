"""L'état de Maestro, le point d'entrée du Director (OPP-02) : sa boîte Orca, ses projets, son bail, et les commandes de sa session.

    python3 ballet_maestro.py mailbox                        # crée la boîte de Maestro, une seule fois
    python3 ballet_maestro.py project add <alias> <chemin>   # enregistre un projet (ou change son chemin)
    python3 ballet_maestro.py project list                   # les projets connus
    python3 ballet_maestro.py claim [--take-over]            # prend le bail : une seule session Maestro lit la boîte
    python3 ballet_maestro.py wait --owner <jeton>           # attend la boîte (en arrière-plan), affiche ce qui arrive
    python3 ballet_maestro.py recap                          # le non-lu et l'historique de la boîte, au démarrage
    python3 ballet_maestro.py status                         # les sessions ouvertes de chaque projet
    python3 ballet_maestro.py tell <projet>#<élément> <texte>   # la réponse du Director, au terminal du Conductor

L'état vit dans `~/.ballet/maestro.toml` (`BALLET_HOME` pour un autre dossier) :

    [mailbox]                 la boîte : un terminal Orca vide, à elle seule, et la Run créée `--from` lui
    terminal = "term_…"
    run = "run_…"
    previous_run = "run_…"    la Run d'une boîte recréée, que `recap` relit une dernière fois puis oublie

    [lease]                   le bail de lecture : lire la boîte consomme les messages, une seule session le fait
    owner = "…"               le jeton de la session Maestro (`claim`) ; vide, personne
    pid = 0                   le processus de son attente en cours (`wait`), 0 sinon
    renewed = "…"             la date ISO de la dernière prise, ou de la fin de la dernière attente

    [projects.antimurphy]     un projet par alias
    path = "/chemin/vers/antimurphy"

Il n'existe jamais deux boîtes : `mailbox` ne fait rien quand le terminal noté vit encore dans Orca, et un verrou
(`maestro.lock`) empêche deux appels de créer chacun la sienne. Chaque écriture passe par un fichier temporaire, puis
un renommage.

Le bail est vivant tant que le `pid` de l'attente tourne, ou que `renewed` a moins de 10 minutes : c'est le temps qu'a la
session, entre deux attentes, pour traiter un message. `claim` refuse un bail vivant ; `claim --take-over` arrête l'attente
de l'ancien propriétaire et le remplace (après un `/clear`, ou une session morte). `wait` ne lit la boîte que pour le jeton
qui tient le bail ; sinon la session n'est plus Maestro.

`wait` note, pour chaque `status` de sujet `<projet>#<élément> · <événement>`, le terminal expéditeur dans
`~/.ballet/conductors.json` : c'est où `tell` écrit. Il lit en consommant (jamais `--peek`) : un message lu n'est plus non lu.

Les Conductors (`ballet_rehearsal.py`, `ballet_workshop.py`) appellent `announce` quand ils écrivent `NEXT: escalate`
ou `NEXT: done` : un message `status`, priorité `high`, sujet `<projet>#<élément> · <événement>`, dans la boîte. Sans
`maestro.toml` ou sans boîte, rien n'est envoyé ; un envoi qui échoue n'arrête jamais le Conductor.
"""

import fcntl
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import tomllib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

CONFIG_NAME = "maestro.toml"
CONDUCTORS_NAME = "conductors.json"
LOCK_NAME = "maestro.lock"
MAILBOX_TITLE = "maestro-mailbox"
MAILBOX_OBJECTIVE = "Maestro's mailbox: the Conductors and the Monitor write here, Maestro reads"
ANNOUNCED = ("escalate", "done")
ALIAS = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
HEADER = "# Maestro (OPP-02), written by ballet_maestro.py: edit it while no Maestro command runs.\n"
LEASE_TTL = timedelta(minutes=10)   # le temps de la session, entre deux attentes, pour traiter un message
WAIT_TIMEOUT_MS = 600_000           # une attente qui expire sans message est relancée : `wait` ne rend la main qu'avec du courrier
RECAP_LIMIT = 10                    # les derniers messages de l'historique relus au démarrage
EMPTY_LEASE = {"owner": "", "pid": 0, "renewed": ""}
CONDUCTOR_SUBJECT = re.compile(r"^(\S+#\S+) · (.+)$")   # `<projet>#<élément> · <événement>`
TARGET = re.compile(r"^[^\s#]+#\S+$")
USAGE = ("usage: mailbox | project add <alias> <path> | project list | claim [--take-over] | wait --owner <token> "
         "| recap | status | tell <project>#<item> <text>")


class MaestroError(Exception):
    """Maestro ne peut pas faire ce qu'on lui demande : le message dit pourquoi."""


class UsageError(Exception):
    pass


# --- les commandes ------------------------------------------------------------


def mailbox(orca, state=None):
    """La boîte de Maestro, créée une seule fois : un terminal Orca vide, puis une Run créée `--from` lui. Si le
    terminal noté vit encore, rien ne change ; sinon une nouvelle boîte le remplace, et l'ancienne Run est gardée
    pour une dernière lecture."""
    with _locked(state):
        config = read_config(state)
        box = config["mailbox"]
        alive = bool(box.get("terminal")) and _terminal_alive(box["terminal"], orca)
        if alive and box.get("run"):
            return f"mailbox already there: terminal {box['terminal']}, run:{box['run']}"
        box = box if alive else _replace_terminal(config, orca, state)
        box["run"] = _new_run(box["terminal"], orca)
        write_config(config, state)
        return f"mailbox created: terminal {box['terminal']}, run:{box['run']}"


def add_project(alias, path, state=None):
    """Enregistre un projet sous son alias, par son chemin absolu ; un alias connu change de chemin."""
    if not ALIAS.match(alias):
        raise MaestroError(f"not an alias: {alias} (lowercase letters, digits, '-' or '_')")
    folder = Path(path).expanduser().resolve()
    if not folder.is_dir():
        raise MaestroError(f"no folder at {folder}")
    with _locked(state):
        config = read_config(state)
        config["projects"][alias] = {"path": str(folder)}
        write_config(config, state)
    return f"project {alias}: {folder}"


def list_projects(state=None):
    projects = read_config(state)["projects"]
    if not projects:
        return "no project yet: python3 ballet_maestro.py project add <alias> <path>"
    return "\n".join(f"{alias}  {project['path']}" for alias, project in sorted(projects.items()))


def announce(step, home, orca, state=None):
    """Prévient Maestro qu'un Conductor escalade ou a fini : un `status` dans sa boîte. Sans boîte, rien n'est
    envoyé ; un échec devient une ligne du pas, jamais une panne."""
    if step.next not in ANNOUNCED or not step.item:
        return
    try:
        config = read_config(state)
    except (OSError, tomllib.TOMLDecodeError) as error:
        step.done.append(f"Maestro not told: {_config_path(state)} unreadable: {error}")
        return
    run = config["mailbox"].get("run")
    if not run:
        return
    subject = f"{project_of(home, config)}#{step.item.lstrip('#')} · {step.next}"
    try:
        orca(["orchestration", "send", "--to", f"run:{run}", "--type", "status", "--priority", "high",
              "--subject", subject, "--body", step.render()])
    except Exception as error:  # l'annonce n'est qu'un plus : rien ne doit arrêter le Conductor
        step.done.append(f"Maestro not told ({subject}): {error}")
        return
    step.done.append(f"Maestro told: {subject}")


def project_of(home, config):
    """L'alias du projet dont `home` est le dossier, sinon le nom du dossier."""
    folder = Path(home).resolve()
    return next((alias for alias, project in config["projects"].items() if Path(project["path"]).resolve() == folder),
                folder.name)


def claim(take_over=False, state=None):
    """Le bail de lecture de la boîte, pour une seule session : refusé quand une autre le tient vivant, sauf `take_over`,
    qui arrête d'abord l'attente de l'ancien propriétaire. Rend le jeton de la nouvelle propriétaire."""
    with _locked(state):
        config = read_config(state)
        lease = config["lease"]
        if _lease_alive(lease) and not take_over:
            raise MaestroError(_lease_held_message(lease))
        _stop_the_wait(lease["pid"])
        owner = secrets.token_hex(8)
        config["lease"] = {"owner": owner, "pid": 0, "renewed": _now()}
        write_config(config, state)
    return f"lease claimed, owner {owner}"


def wait(owner, orca, state=None):
    """Attend un message dans la boîte, puis le rend lisible. Seul le jeton qui tient le bail lit : lire consomme.
    L'attente se note dans le bail (son pid) le temps qu'elle dure, et note le terminal de chaque Conductor qui écrit."""
    box = _take_the_wait(owner, state)
    try:
        messages = _wait_for_messages(box, orca)
        _note_conductors(messages, state)
    finally:
        _release_the_wait(owner, state)
    return _render_messages(messages)


def recap(orca, state=None):
    """Ce qui s'est dit dans la boîte pendant l'absence de la session : le non-lu et les derniers messages de
    l'historique (un message lu juste avant sa mort n'est plus non lu), ceux de la boîte précédente comprise, qu'on
    oublie ensuite."""
    config = read_config(state)
    box = _checked_mailbox(config)
    runs = [box["run"], *([box["previous_run"]] if box.get("previous_run") else [])]
    history = [message for run in runs for message in _history_of(run, orca)]
    _forget_previous_run(state)
    return _render_history(sorted(history, key=lambda message: message["sequence"])[-RECAP_LIMIT:])


def status(state=None):
    """Les sessions ouvertes de chaque projet, une ligne chacune : élément, Rehearsal courante, état, terminal connu."""
    config = read_config(state)
    registry = read_conductors(state)
    lines = [_session_line(alias, session, registry) for alias, project in sorted(config["projects"].items())
             for session in _open_sessions(Path(project["path"]))]
    return "\n".join(lines) or "no open session in any project"


def tell(target, text, orca, state=None):
    """La réponse du Director, tapée dans le terminal du Conductor de `<projet>#<élément>` : le Conductor l'écrit en
    message Ballet et la reçoit lui-même. Un élément inconnu, ou un terminal disparu, est refusé."""
    handle = _known_terminal(target, read_conductors(state))
    if not _terminal_alive(handle, orca):
        raise MaestroError(f"the terminal {handle} of {target} is gone: the Conductor is not running anymore")
    orca(["terminal", "send", "--terminal", handle, "--text", f"Director answers: {text}", "--enter"])
    return f"told {target} (terminal {handle})"


# --- le bail ---------------------------------------------------------------


def _lease_alive(lease):
    """Vivant : un propriétaire dont l'attente tourne, ou qui a renouvelé le bail il y a moins de dix minutes."""
    return bool(lease["owner"]) and (_wait_runs(lease["pid"]) or _renewed_recently(lease["renewed"]))


def _renewed_recently(renewed):
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(renewed) < LEASE_TTL
    except ValueError:   # pas de date, ou illisible : le bail n'a pas été renouvelé
        return False


def _lease_held_message(lease):
    where = f"its wait is running (pid {lease['pid']})" if _wait_runs(lease["pid"]) else f"renewed {lease['renewed']}"
    return (f"another Maestro session holds the lease ({where}). Two sessions reading the mailbox would steal each "
            "other's messages. If that session is gone, or you cleared it, take over: claim --take-over")


def _stop_the_wait(pid):
    if _wait_runs(pid):
        os.kill(pid, signal.SIGTERM)


def _wait_runs(pid):
    """Le processus est-il encore une attente de Maestro ? Un pid qu'un autre programme a repris ne compte pas."""
    if not pid or pid <= 0:
        return False
    shown = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
    return "ballet_maestro.py" in shown and " wait" in shown


def _take_the_wait(owner, state):
    """Le jeton tient le bail et aucune autre attente ne tourne pour lui : l'attente note son pid. Rend la boîte."""
    with _locked(state):
        config = read_config(state)
        lease = config["lease"]
        if lease["owner"] != owner:
            raise MaestroError("this session is not Maestro anymore: " + _who_holds(lease))
        if _wait_runs(lease["pid"]) and lease["pid"] != os.getpid():
            raise MaestroError(f"a wait of this session is already running (pid {lease['pid']}): one at a time")
        box = _checked_mailbox(config)
        config["lease"] = {**lease, "pid": os.getpid(), "renewed": _now()}
        write_config(config, state)
    return box


def _release_the_wait(owner, state):
    """L'attente finie : pid remis à 0 et bail renouvelé, sauf si un autre a pris le bail entre-temps."""
    with _locked(state):
        config = read_config(state)
        if config["lease"]["owner"] != owner:
            return
        config["lease"] = {**config["lease"], "pid": 0, "renewed": _now()}
        write_config(config, state)


def _who_holds(lease):
    if not lease["owner"]:
        return "no lease is held, run claim"
    return "another session holds the lease, ask the Director whether to claim --take-over"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _stopped_by_take_over():
    """Un `SIGTERM` (un autre Maestro prend le bail) arrête l'attente, et Orca avec elle : la session en est prévenue."""
    def stop(signum, frame):
        raise MaestroError("this session is not Maestro anymore: its wait was stopped (another session took over)")
    previous = signal.signal(signal.SIGTERM, stop)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


# --- la boîte, lue ------------------------------------------------------------


def _checked_mailbox(config):
    box = config["mailbox"]
    if not box.get("terminal") or not box.get("run"):
        raise MaestroError("no mailbox yet: run ballet_maestro.py mailbox")
    return box


def _wait_for_messages(box, orca):
    """Une lecture qui consomme (jamais `--peek`), bloquée jusqu'au premier message ; une attente qui expire repart."""
    while True:
        answer = json.loads(orca(["orchestration", "check", "--terminal", box["terminal"], "--run", box["run"],
                                  "--wait", "--timeout-ms", str(WAIT_TIMEOUT_MS), "--json"]))
        if answer["result"]["messages"]:
            return answer["result"]["messages"]


def _history_of(run, orca):
    """Les derniers messages d'une Run de boîte, lus ou non (l'historique ne consomme rien)."""
    answer = json.loads(orca(["orchestration", "inbox", "--terminal", f"run:{run}", "--limit", str(RECAP_LIMIT), "--full", "--json"]))
    return [message for message in answer["result"]["messages"] if message["run_id"] == run]


def _forget_previous_run(state):
    with _locked(state):
        config = read_config(state)
        if config["mailbox"].pop("previous_run", None):
            write_config(config, state)


def _render_messages(messages):
    return "\n\n".join(_message_text(message) for message in messages)


def _render_history(messages):
    if not messages:
        return "the mailbox is empty"
    unread = sum(1 for message in messages if not message["read"])
    shown = "\n\n".join(_message_text(message, tag="unread" if not message["read"] else "read") for message in messages)
    return f"{len(messages)} message(s), {unread} unread (a wait will deliver the unread ones again):\n\n{shown}"


def _message_text(message, tag=""):
    sender = message.get("from") or message.get("from_handle", "?")
    head = f"[{message.get('priority', 'normal')}] {message.get('type', 'message')} from {sender}"
    when = f" · {message['created_at']}" if message.get("created_at") else ""
    return f"{head}{when}{' · ' + tag if tag else ''}\nSubject: {message.get('subject', '')}\n{message.get('body', '')}".rstrip()


# --- conductors.json ------------------------------------------------------------


def read_conductors(state=None):
    """Le registre minimal des Conductors : `<projet>#<élément>` → son terminal, vu quand, son dernier événement."""
    path = _conductors_path(state)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _note_conductors(messages, state):
    """Chaque `status` de sujet `<projet>#<élément> · <événement>` dit où est son Conductor : son terminal expéditeur."""
    seen = {}
    for message in messages:
        found = CONDUCTOR_SUBJECT.match(message.get("subject", ""))
        if message.get("type") == "status" and found and message.get("from"):
            seen[found.group(1)] = {"terminal": message["from"], "seen": _now(), "event": found.group(2)}
    if not seen:
        return
    with _locked(state):
        registry = {**read_conductors(state), **seen}
        _write_atomically(_conductors_path(state), json.dumps(registry, indent=2, ensure_ascii=False) + "\n")


def _known_terminal(target, registry):
    if not TARGET.match(target):
        raise MaestroError(f"not an item: {target} (expected <project>#<item>, e.g. antimurphy#12)")
    if target not in registry:
        known = ", ".join(sorted(registry)) or "none yet"
        raise MaestroError(f"no terminal known for {target}: a Conductor is known once it escalates or finishes (known: {known})")
    return registry[target]["terminal"]


def _conductors_path(state=None):
    return _state_dir(state) / CONDUCTORS_NAME


# --- les sessions d'un projet -----------------------------------------------------


def _open_sessions(home):
    """Les sessions ouvertes d'un projet, Rehearsal puis Workshop, lues avec les fonctions de leurs scripts. Ces
    scripts importent celui-ci : l'import se fait ici, pas en tête. Un projet sans `.ballet/run/` n'a aucune session
    (et rien n'y est créé). Chacune : (élément, Rehearsal courante, état)."""
    import ballet_rehearsal
    import ballet_workshop
    if not (home / ballet_rehearsal.RUN_DIR).is_dir():
        return []
    rehearsals = [(session.item, session.current or "-", _rehearsal_state(session, home))
                  for session in ballet_rehearsal._open_sessions(home)]
    workshops = [(workshop.item, "Workshop", workshop.status) for workshop in ballet_workshop._open_workshops(home)]
    return rehearsals + workshops


def _rehearsal_state(session, home):
    """L'état de la Rehearsal en cours (open, escalated…) ; celui de la session tant qu'aucune n'est lisible."""
    import ballet_rehearsal
    try:
        return ballet_rehearsal._load(session.current, home).status if session.current else session.status
    except ballet_rehearsal.RehearsalError:
        return session.status


def _session_line(alias, session, registry):
    item, rehearsal, state = session
    terminal = registry.get(f"{alias}#{item.lstrip('#')}", {}).get("terminal", "no terminal known")
    return f"{alias}  {item}  {rehearsal}  {state}  {terminal}"


# --- maestro.toml -------------------------------------------------------------


def read_config(state=None):
    """L'état de Maestro, avec ses trois tables toujours présentes (le bail avec ses trois clés) ; pas de fichier, un état vide."""
    path = _config_path(state)
    config = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    config.setdefault("mailbox", {})
    saved = config.get("lease", {})
    config["lease"] = {key: saved.get(key, empty) for key, empty in EMPTY_LEASE.items()}
    config.setdefault("projects", {})
    return config


def write_config(config, state=None):
    """Écrit l'état d'un coup, par un fichier temporaire puis un renommage."""
    _write_atomically(_config_path(state), to_toml(config))


def _write_atomically(path, text):
    """Un fichier temporaire à côté, puis un renommage ; un lecteur voit l'ancien contenu ou le nouveau, jamais la moitié."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def to_toml(config):
    """Un TOML lisible : les valeurs simples d'une table, puis ses sous-tables, chacune sous son en-tête."""
    return HEADER + "\n".join(_table_lines(config, ())).lstrip("\n") + "\n"


def _table_lines(table, path):
    lines = [f"{_key(key)} = {_value(value)}" for key, value in table.items() if not isinstance(value, dict)]
    for key, sub in table.items():
        if isinstance(sub, dict):
            sub_path = (*path, key)
            if not sub or any(not isinstance(value, dict) for value in sub.values()):
                lines += ["", f"[{'.'.join(_key(part) for part in sub_path)}]"]
            lines += _table_lines(sub, sub_path)
    return lines


def _key(key):
    return key if BARE_KEY.match(key) else json.dumps(key, ensure_ascii=False)


def _value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)   # une chaîne JSON est une chaîne de base TOML
    if isinstance(value, list):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    raise MaestroError(f"cannot write {type(value).__name__} in {CONFIG_NAME}")


def _state_dir(state=None):
    return Path(state or os.environ.get("BALLET_HOME") or Path.home() / ".ballet")


def _config_path(state=None):
    return _state_dir(state) / CONFIG_NAME


@contextmanager
def _locked(state=None):
    """Un seul appel de Maestro à la fois modifie son état."""
    folder = _state_dir(state)
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / LOCK_NAME, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


# --- Orca ---------------------------------------------------------------------


def _terminal_alive(handle, orca):
    """Le terminal vit-il encore dans Orca ? Une Orca injoignable lève : on ne recrée jamais une boîte à l'aveugle."""
    return handle in _texts(json.loads(orca(["terminal", "list", "--json"])))


def _replace_terminal(config, orca, state):
    """Un nouveau terminal vide pour la boîte, noté aussitôt (avant sa Run) : un appel qui échoue ensuite le retrouve."""
    previous_run = config["mailbox"].get("run")
    receipt = json.loads(orca(["terminal", "create", "--title", MAILBOX_TITLE, "--json"]))
    terminal = _first_id(receipt, "term_", "orca terminal create")
    config["mailbox"] = {"terminal": terminal, **({"previous_run": previous_run} if previous_run else {})}
    write_config(config, state)
    return config["mailbox"]


def _new_run(terminal, orca):
    receipt = json.loads(orca(["orchestration", "run-create", "--objective", MAILBOX_OBJECTIVE, "--from", terminal, "--json"]))
    return _first_id(receipt, "run_", "orca orchestration run-create")


def _first_id(receipt, prefix, command):
    found = next((text for text in _texts(receipt) if text.startswith(prefix)), None)
    if not found:
        raise MaestroError(f"{command} returned no {prefix}… id: {json.dumps(receipt)[:300]}")
    return found


def _texts(value):
    """Toutes les chaînes d'un reçu JSON d'Orca, où qu'elles soient."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _texts(item)
    elif isinstance(value, list):
        for item in value:
            yield from _texts(item)


def _orca(arguments):
    completed = subprocess.run([os.environ.get("ORCA_CLI_COMMAND", "orca"), *arguments], capture_output=True, text=True)
    if completed.returncode != 0:
        raise MaestroError(completed.stderr.strip() or completed.stdout.strip() or "orca failed")
    return completed.stdout


# --- ligne de commande --------------------------------------------------------


def main(argv, orca=None):
    """Affiche le résultat et sort avec 0 ; 1 si Maestro ne peut pas le faire, 2 sur un usage invalide."""
    try:
        print(_command(argv[1:], orca or _orca))
    except UsageError as error:
        print(error, file=sys.stderr)
        return 2
    except (MaestroError, OSError, tomllib.TOMLDecodeError, json.JSONDecodeError) as error:
        print(f"maestro: {error}", file=sys.stderr)
        return 1
    return 0


def _command(arguments, orca):
    if arguments == ["mailbox"]:
        return mailbox(orca)
    if arguments[:2] == ["project", "add"] and len(arguments) == 4:
        return add_project(arguments[2], arguments[3])
    if arguments == ["project", "list"]:
        return list_projects()
    if arguments in (["claim"], ["claim", "--take-over"]):
        return claim(take_over="--take-over" in arguments)
    if arguments[:2] == ["wait", "--owner"] and len(arguments) == 3:
        with _stopped_by_take_over():
            return wait(arguments[2], orca)
    if arguments == ["recap"]:
        return recap(orca)
    if arguments == ["status"]:
        return status()
    if arguments[:1] == ["tell"] and len(arguments) >= 3:
        return tell(arguments[1], " ".join(arguments[2:]), orca)
    raise UsageError(USAGE)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
