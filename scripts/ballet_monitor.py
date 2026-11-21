"""Le Monitor de Ballet (OPP-01, OPP-02 étape 4) : un script sans LLM qui observe et signale à Maestro.

    python3 ballet_monitor.py once                   # un seul tour (à la main, pour essayer)
    python3 ballet_monitor.py run [--interval <s>]   # en boucle, 180 s par défaut : dans son propre terminal Orca

Il ne lance jamais rien et ne parle jamais au Director : il écrit dans la boîte de Maestro, depuis son terminal Orca
(`ORCA_TERMINAL_HANDLE`, comme les Conductors), et Maestro décide. Deux choses seulement :

- **Un élément passé `ready`.** Pour chaque projet de `maestro.toml`, la file GitHub est lue par `ballet_program.py` (les
  `Feature`, `Bug` et `Task` au champ `Ballet status` `ready`). Chaque élément nouvellement prêt devient un `status`,
  sujet `<projet>#<N> · ready`, corps `#<N> · <type> · <priorité> · <titre> · <lien>`. Au premier tour d'un projet, les
  éléments déjà prêts sont groupés en un seul message (sujet `<projet> · ready (<n> already)`, une ligne par élément).
  Les éléments prêts de chaque projet sont gardés dans `~/.ballet/monitor.json` (`BALLET_HOME` pour un autre dossier,
  écriture atomique sous verrou) : un élément encore prêt au tour suivant n'est pas signalé deux fois ; un élément qui
  quitte `ready` puis y revient l'est de nouveau. C'est aussi ce que lit `ballet_maestro.py ready`.
- **Un Conductor disparu.** Une ligne `running` du registre dont le terminal n'existe plus dans Orca devient un `status`
  `<projet>#<élément> · gone`, priorité `high`, et la ligne passe à `gone`, une seule fois. Un Conductor figé (terminal
  vivant, rien d'envoyé) n'est pas vu ici : c'est une autre opportunité.

Un envoi qui échoue n'est pas noté comme fait : le tour suivant le refait. `gh` ou Orca injoignable est une ligne d'erreur
du tour, jamais une panne de `run`.
"""

import json
import re
import sys
import time
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import ballet_conductors
import ballet_maestro
import ballet_program
import ballet_state
from ballet_maestro import MaestroError

STATE_NAME = "monitor.json"
LOCK_NAME = "monitor.lock"
DEFAULT_INTERVAL = 180
KEPT = ("item", "number", "type", "title", "priority", "url")   # ce que le Monitor retient d'un élément prêt
READY_LINE = re.compile(r"^#(?P<number>\d+) · (?P<type>\w+) · ")
READY_SUBJECT = re.compile(r"^([^\s#]+)(?:#\S+)? · ready\b")
USAGE = "usage: once | run [--interval <seconds>]"


class UsageError(Exception):
    pass


@dataclass
class Report:
    """Ce qu'un tour a dit à Maestro, et ce qui l'a gêné."""
    told: list = field(default_factory=list)
    errors: list = field(default_factory=list)


# --- les tours ----------------------------------------------------------------


def once(orca, queue=ballet_program.ready_items, state=None):
    """Un tour : la file de chaque projet, puis les Conductors dont le terminal a disparu."""
    report = Report()
    for alias, home in _projects(state):
        _attempt(report, alias, lambda: _watch_ready(alias, home, orca, queue, state, report))
    _attempt(report, "Conductors", lambda: _watch_gone(orca, state, report))
    return report


def run(interval, orca, queue=ballet_program.ready_items, state=None, tours=None, sleep=time.sleep):
    """Des tours à la suite, `interval` secondes entre deux ; `tours` les borne (les tests). Une erreur ne l'arrête pas."""
    done = 0
    while tours is None or done < tours:
        if done:
            sleep(interval)
        done += 1
        try:
            report = once(orca, queue, state)
        except Exception as error:  # le Monitor doit survivre à ce qu'il n'a pas prévu : le tour suivant réessaie
            report = Report(errors=[f"turn failed: {error}"])
        _show(report)


def _attempt(report, label, step):
    """Une panne d'un projet ou d'Orca est une ligne d'erreur ; les autres étapes du tour continuent."""
    try:
        step()
    except (ballet_program.ProgramError, MaestroError, OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        report.errors.append(f"{label}: {error}")


def _projects(state):
    projects = ballet_maestro.read_config(state)["projects"]
    return [(alias, Path(project["path"])) for alias, project in sorted(projects.items())]


# --- un élément passé ready ----------------------------------------------------


def _watch_ready(alias, home, orca, queue, state, report):
    """Signale ce qui est nouvellement prêt, puis retient la file telle qu'elle est : ce qui en est sorti pourra revenir."""
    items = [_kept(item) for item in queue(home)]
    known = read_ready(state).get(alias)
    if known is None:
        _tell_first_turn(alias, items, orca, state, report)
    else:
        for item in _newly_ready(items, known):
            _tell_ready(alias, item, orca, state, report)
            known = [*known, item]
            _save_ready(alias, known, state)
    _save_ready(alias, items, state)


def _tell_first_turn(alias, items, orca, state, report):
    """Au premier tour d'un projet : un seul message pour tous les éléments déjà prêts, pour ne pas inonder la boîte."""
    if not items:
        return
    subject = f"{alias} · ready ({len(items)} already)"
    _send(subject, "\n".join(_ready_line(item) for item in items), "normal", orca, state, report)


def _tell_ready(alias, item, orca, state, report):
    _send(f"{alias}#{item['number']} · ready", _ready_line(item), "normal", orca, state, report)


def _newly_ready(items, known):
    already = {item["item"] for item in known}
    return [item for item in items if item["item"] not in already]


def _ready_line(item):
    return f"#{item['number']} · {item['type']} · {item['priority'] or 'no priority'} · {item['title']} · {item['url']}"


def _kept(item):
    return {name: item[name] for name in KEPT}


def project_of_ready_subject(subject):
    """L'alias du projet d'un sujet `<projet>#<N> · ready` ou `<projet> · ready (…)` ; vide pour tout autre sujet."""
    found = READY_SUBJECT.match(subject)
    return found.group(1) if found else ""


# --- un Conductor disparu ------------------------------------------------------


def _watch_gone(orca, state, report):
    """Chaque Conductor `running` dont le terminal n'est plus dans Orca : signalé puis marqué `gone`, une fois."""
    running = {key: line for key, line in ballet_conductors.read(state).items()
               if ballet_conductors.state_of(line) == ballet_conductors.RUNNING}
    if not running:
        return
    alive = ballet_maestro.live_terminals(orca)
    for key, line in sorted(running.items()):
        if line["terminal"] not in alive:
            _attempt(report, key, lambda: _tell_gone(key, line, orca, state, report))


def _tell_gone(key, line, orca, state, report):
    body = (f"The Conductor of {key} is gone: its terminal {line['terminal']} no longer exists in Orca "
            f"({line.get('kind') or 'kind unknown'}, started {line.get('started') or 'at an unknown time'}, "
            f"last event {line.get('event') or 'none'}). Relaunch it only on the Director's word.")
    _send(f"{key} · gone", body, "high", orca, state, report)
    ballet_conductors.mark_gone(key, line["terminal"], state)


# --- la boîte ------------------------------------------------------------------


def _send(subject, body, priority, orca, state, report):
    ballet_maestro.post_status(ballet_maestro.mailbox_run(state), subject, body, priority, orca)
    report.told.append(subject)


# --- monitor.json --------------------------------------------------------------


def read_ready(state=None):
    """Les éléments prêts de chaque projet, tels que le dernier tour les a vus : alias → éléments, dans l'ordre de la
    file. Un projet pas encore vu n'y figure pas."""
    path = _path(state)
    if not path.is_file():
        return {}
    return {alias: project["ready"] for alias, project in json.loads(path.read_text(encoding="utf-8"))["projects"].items()}


def _save_ready(alias, items, state):
    with ballet_state.locked(state, LOCK_NAME):
        ready = read_ready(state)
        ready[alias] = items
        document = {"projects": {name: {"ready": found} for name, found in ready.items()}}
        ballet_state.write_atomically(_path(state), json.dumps(document, indent=2, ensure_ascii=False) + "\n")


def _path(state=None):
    return ballet_state.state_dir(state) / STATE_NAME


# --- ligne de commande ---------------------------------------------------------


def _show(report):
    """Une ligne par message envoyé ou erreur, datée ; rien quand le tour n'a rien à dire."""
    stamp = datetime.now().strftime("%H:%M:%S")
    for subject in report.told:
        print(f"{stamp} told Maestro: {subject}", flush=True)
    for error in report.errors:
        print(f"{stamp} problem: {error}", file=sys.stderr, flush=True)


def main(argv, orca=None, queue=ballet_program.ready_items):
    """Un tour (`once`, 1 s'il a eu un problème) ou des tours sans fin (`run`) ; 2 sur un usage invalide."""
    orca = orca or ballet_maestro.run_orca
    try:
        arguments = argv[1:]
        if arguments == ["once"]:
            report = once(orca, queue)
            _show(report)
            if not report.told and not report.errors:
                print("nothing new")
            return 1 if report.errors else 0
        if arguments[:1] == ["run"]:
            run(_interval(arguments[1:]), orca, queue)
            return 0
        raise UsageError(USAGE)
    except UsageError as error:
        print(error, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


def _interval(arguments):
    if not arguments:
        return DEFAULT_INTERVAL
    if len(arguments) == 2 and arguments[0] == "--interval":
        try:
            seconds = float(arguments[1])
        except ValueError:
            seconds = 0
        if seconds > 0:
            return seconds
    raise UsageError(USAGE)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
