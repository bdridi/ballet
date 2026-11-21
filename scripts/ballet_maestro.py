"""L'état de Maestro, le point d'entrée du Director (OPP-02) : sa boîte Orca, ses projets, et l'annonce des Conductors.

    python3 ballet_maestro.py mailbox                        # crée la boîte de Maestro, une seule fois
    python3 ballet_maestro.py project add <alias> <chemin>   # enregistre un projet (ou change son chemin)
    python3 ballet_maestro.py project list                   # les projets connus

L'état vit dans `~/.ballet/maestro.toml` (`BALLET_HOME` pour un autre dossier) :

    [mailbox]                 la boîte : un terminal Orca vide, à elle seule, et la Run créée `--from` lui
    terminal = "term_…"
    run = "run_…"
    previous_run = "run_…"    la Run d'une boîte recréée, que Maestro relit une dernière fois

    [lease]                   le bail de lecture (étape 2 d'OPP-02) : une seule session Maestro lit la boîte
    pid = 0                   le processus de son attente
    since = ""                son début

    [projects.antimurphy]     un projet par alias
    path = "/chemin/vers/antimurphy"

Il n'existe jamais deux boîtes : `mailbox` ne fait rien quand le terminal noté vit encore dans Orca, et un verrou
(`maestro.lock`) empêche deux appels de créer chacun la sienne. Chaque écriture passe par un fichier temporaire, puis
un renommage.

Les Conductors (`ballet_rehearsal.py`, `ballet_workshop.py`) appellent `announce` quand ils écrivent `NEXT: escalate`
ou `NEXT: done` : un message `status`, priorité `high`, sujet `<projet>#<élément> · <événement>`, dans la boîte. Sans
`maestro.toml` ou sans boîte, rien n'est envoyé ; un envoi qui échoue n'arrête jamais le Conductor.
"""

import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from contextlib import contextmanager
from pathlib import Path

CONFIG_NAME = "maestro.toml"
LOCK_NAME = "maestro.lock"
MAILBOX_TITLE = "maestro-mailbox"
MAILBOX_OBJECTIVE = "Maestro's mailbox: the Conductors and the Monitor write here, Maestro reads"
ANNOUNCED = ("escalate", "done")
ALIAS = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
HEADER = "# Maestro (OPP-02), written by ballet_maestro.py: edit it while no Maestro command runs.\n"
USAGE = "usage: mailbox | project add <alias> <path> | project list"


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


# --- maestro.toml -------------------------------------------------------------


def read_config(state=None):
    """L'état de Maestro, avec ses trois tables toujours présentes ; pas de fichier, un état vide."""
    path = _config_path(state)
    config = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    config.setdefault("mailbox", {})
    config.setdefault("lease", {"pid": 0, "since": ""})
    config.setdefault("projects", {})
    return config


def write_config(config, state=None):
    """Écrit l'état d'un coup : un fichier temporaire à côté, puis un renommage ; un lecteur voit l'ancien ou le nouveau."""
    path = _config_path(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{CONFIG_NAME}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(to_toml(config))
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
    raise UsageError(USAGE)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
