"""Le lancement des Conductors par Maestro (OPP-02, étape 3) : un terminal Orca dans le projet, où tourne Claude.

    python3 ballet_launch.py rehearsal <projet> <élément>       # `#12`, `12` ou `FEAT-002`
    python3 ballet_launch.py workshop <projet> [<élément>]      # un Workshop autopilot : `BUG-004`, ou la première ligne de *Next up*

Maestro seul l'appelle (sur la demande du Director, plus tard sur celle du Monitor) : c'est le seul lanceur de Ballet.

Le Conductor est `claude --remote-control '<projet>#<élément>' '<prompt>' --allowedTools 'Bash(python3:*)' 'Edit(.ballet/run/**)'`, lancé par
`orca terminal create --worktree path:<projet> --command …`. Le prompt vient avant les options : `--allowedTools` prend
tout ce qui la suit pour ses valeurs. Un Conductor ne lance que les scripts de Ballet (`python3`) : `gh`, `git` et `orca`
sont appelés par ces scripts, jamais par l'agent. Il n'écrit qu'un fichier, le message Ballet du Director
(`.ballet/run/inbox.md`) : `Edit(.ballet/run/**)` le laisse faire sans demande de permission, quel que soit le mode. `BALLET_CONDUCTOR_COMMAND` remplace `claude` (un autre agent, ou une
commande inoffensive pour essayer sans tokens) ; les arguments restent les mêmes.

Avant tout lancement, quatre garde-fous, chacun avec son refus : le projet est connu de `maestro.toml` ; l'élément n'a pas
déjà un Conductor vivant (dans le registre, ou en session ouverte dans le projet) ; le plafond de Conductors simultanés
n'est pas atteint ; le plafond de lancements du jour non plus. Les plafonds sont ceux de la table `[limits]` de
`maestro.toml` (`max_running`, `max_per_day`).

Le lancement écrit sa ligne dans le registre (`ballet_conductors.py`) : projet, élément, genre, terminal, début. L'URL
Remote Control de la session s'y ajoute si on la lit dans le terminal dans les secondes qui suivent ; sinon elle reste vide.
"""

import json
import os
import re
import shlex
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

import ballet_conductors
import ballet_maestro
import ballet_rehearsal
import ballet_state
import ballet_workshop
from ballet_maestro import MaestroError

COMMAND_VARIABLE = "BALLET_CONDUCTOR_COMMAND"
DEFAULT_AGENT = "claude"
ALLOWED_TOOLS = ("Bash(python3:*)", "Edit(.ballet/run/**)")
DEFAULT_LIMITS = {"max_running": 3, "max_per_day": 10}
LAUNCH_LOCK = "launch.lock"
REMOTE_CONTROL_URL = re.compile(r"https://claude\.ai/code/\S+")
URL_WAIT_SECONDS = 8
URL_POLL_SECONDS = 1
USAGE = "usage: rehearsal <project> <item> | workshop <project> [<item>]"


class LaunchError(Exception):
    """Maestro ne lance pas ce Conductor : le message dit pourquoi."""


class UsageError(Exception):
    pass


@dataclass
class Launch:
    """Un Conductor à lancer : son projet, son élément (tel que le notent les Conductors), son genre et son prompt."""
    project: str
    home: Path
    item: str
    kind: str
    prompt: str

    @property
    def key(self):
        return f"{self.project}#{self.item}"


# --- les commandes ------------------------------------------------------------


def launch_rehearsal(project, item, orca, state=None, url_wait=URL_WAIT_SECONDS):
    """Lance le Conductor de `/ballet:rehearsal` sur un élément : `#12`, `12` ou `FEAT-002`."""
    home = _known_project(project, state)
    key_item, prompt_item = _rehearsal_item(item)
    return _launch(Launch(project, home, key_item, "rehearsal", f"/ballet:rehearsal {prompt_item}"), orca, state, url_wait)


def launch_workshop(project, item, orca, state=None, url_wait=URL_WAIT_SECONDS):
    """Lance le Conductor de `/ballet:workshop --autopilot` sur un élément du backlog ; sans élément, la première ligne de
    *Next up* du projet."""
    home = _known_project(project, state)
    chosen = _workshop_item(item, home)
    return _launch(Launch(project, home, chosen, "workshop", f"/ballet:workshop --autopilot {chosen}"), orca, state, url_wait)


def _launch(launch, orca, state, url_wait):
    """Les garde-fous, le terminal, la ligne du registre, puis l'URL Remote Control : un lancement à la fois."""
    with ballet_state.locked(state, LAUNCH_LOCK):
        _check_guardrails(launch, orca, state)
        terminal = _open_terminal(launch, orca)
        ballet_conductors.record_launch(launch.key, launch.project, launch.item, launch.kind, terminal, state)
        url = _find_remote_control_url(terminal, orca, url_wait)
        if url:
            ballet_conductors.note_url(launch.key, url, state)
    return _report(launch, terminal, url)


# --- les garde-fous --------------------------------------------------------------


def _check_guardrails(launch, orca, state):
    """Chaque refus nomme ce qui bloque ; rien n'est créé avant que tous soient passés. Orca injoignable : on ne lance pas à l'aveugle."""
    registry = ballet_conductors.read(state)
    alive = ballet_maestro.live_terminals(orca)
    config = ballet_maestro.read_config(state)
    _refuse_if_running_in_registry(launch, registry, alive)
    _refuse_if_session_open(launch)
    _refuse_if_too_many_running(registry, alive, config)
    _refuse_if_too_many_today(registry, config)


def _known_project(project, state):
    projects = ballet_maestro.read_config(state)["projects"]
    if project not in projects:
        raise LaunchError(f"unknown project {project} (known: {', '.join(sorted(projects)) or 'none'}): "
                          "register it with ballet_maestro.py project add <alias> <path>")
    home = Path(projects[project]["path"])
    if not home.is_dir():
        raise LaunchError(f"the folder of {project} is gone: {home}")
    return home


def _refuse_if_running_in_registry(launch, registry, alive):
    line = registry.get(launch.key)
    if line and _is_running(line, alive):
        raise LaunchError(f"{launch.key} already has a Conductor running, in terminal {line['terminal']}: "
                          "talk to it (tell), do not launch another")


def _refuse_if_session_open(launch):
    for item, current, state in ballet_maestro.sessions_of(launch.home):
        if item.lstrip("#") == launch.item:
            raise LaunchError(f"{launch.key} has an open session in {launch.home} (state {state}, Rehearsal {current}): "
                              "its Conductor must pick it up, not a new launch")


def _refuse_if_too_many_running(registry, alive, config):
    limit = _limit(config, "max_running")
    running = sorted(key for key, line in registry.items() if _is_running(line, alive))
    if len(running) >= limit:
        raise LaunchError(f"{len(running)} Conductor(s) already running ({', '.join(running)}): the limit is {limit} "
                          f"([limits] max_running in {ballet_maestro.CONFIG_NAME})")


def _refuse_if_too_many_today(registry, config):
    limit = _limit(config, "max_per_day")
    today = ballet_conductors.launches_today(registry)
    if today >= limit:
        raise LaunchError(f"{today} launch(es) today already: the limit is {limit} ([limits] max_per_day in {ballet_maestro.CONFIG_NAME})")


def _is_running(line, alive):
    """Un Conductor vit quand sa ligne n'est pas close et que son terminal est encore ouvert dans Orca."""
    return ballet_conductors.state_of(line) == ballet_conductors.RUNNING and line["terminal"] in alive


def _limit(config, name):
    value = config.get("limits", {}).get(name, DEFAULT_LIMITS[name])
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LaunchError(f"[limits] {name} in {ballet_maestro.CONFIG_NAME} must be a whole number, not {value!r}")
    return value


# --- l'élément -------------------------------------------------------------------


def _rehearsal_item(text):
    """(l'élément comme les Conductors le notent, l'élément comme `/ballet:rehearsal` le prend) : `#12` et `12` sont le même."""
    issue = ballet_rehearsal.ISSUE_ITEM.match(text)
    if issue:
        return issue.group(1), f"#{issue.group(1)}"
    if ballet_rehearsal.FEATURE_ITEM.match(text):
        return text, text
    raise LaunchError(f"not an item: {text} (expected #12, 12 or FEAT-002)")


def _workshop_item(text, home):
    if text:
        if not ballet_workshop.WORKSHOP_ITEM.match(text):
            raise LaunchError(f"not a backlog item: {text} (expected OPP-12, FEAT-007, BUG-004 or TASK-009, or none)")
        return text
    try:
        return ballet_workshop.next_item(home)
    except ballet_workshop.WorkshopError as error:
        raise LaunchError(str(error)) from error


# --- le terminal ------------------------------------------------------------------


def _open_terminal(launch, orca):
    receipt = json.loads(orca(["terminal", "create", "--worktree", f"path:{launch.home}", "--title", launch.key,
                               "--command", _conductor_command(launch), "--json"]))
    return ballet_maestro.first_id(receipt, "term_", "orca terminal create")


def _conductor_command(launch):
    """`<agent> --remote-control <nom> <prompt> --allowedTools …` : le prompt avant les options."""
    agent = shlex.split(os.environ.get(COMMAND_VARIABLE) or DEFAULT_AGENT)
    return shlex.join([*agent, "--remote-control", launch.key, launch.prompt, "--allowedTools", *ALLOWED_TOOLS])


def _find_remote_control_url(terminal, orca, wait_seconds):
    """L'URL que Claude affiche à son démarrage, lue dans le terminal pendant quelques secondes ; vide si elle ne vient pas."""
    deadline = time.monotonic() + wait_seconds
    while True:
        found = REMOTE_CONTROL_URL.search(_read_terminal(terminal, orca))
        if found:
            return found.group(0)
        if time.monotonic() >= deadline:
            return ""
        time.sleep(URL_POLL_SECONDS)


def _read_terminal(terminal, orca):
    """Ce qui est affiché dans le terminal ; rien quand Orca ne le lit pas : l'URL n'est qu'un plus."""
    try:
        receipt = json.loads(orca(["terminal", "read", "--terminal", terminal, "--screen", "--json"]))
    except (MaestroError, json.JSONDecodeError):
        return ""
    return "\n".join(map(str, receipt.get("result", {}).get("terminal", {}).get("tail", [])))


def _report(launch, terminal, url):
    remote = f"Remote Control {url}" if url else "Remote Control URL not found yet"
    return (f"launched the {launch.kind} Conductor of {launch.key} in {launch.home}: terminal {terminal}, {remote}")


# --- ligne de commande --------------------------------------------------------


def main(argv, orca=None):
    """Affiche ce qui est parti et sort avec 0 ; 1 si le lancement est refusé, 2 sur un usage invalide."""
    try:
        print(_command(argv[1:], orca or ballet_maestro.run_orca))
    except UsageError as error:
        print(error, file=sys.stderr)
        return 2
    except (LaunchError, MaestroError, OSError, tomllib.TOMLDecodeError, json.JSONDecodeError) as error:
        print(f"launch: {error}", file=sys.stderr)
        return 1
    return 0


def _command(arguments, orca):
    if arguments[:1] == ["rehearsal"] and len(arguments) == 3:
        return launch_rehearsal(arguments[1], arguments[2], orca)
    if arguments[:1] == ["workshop"] and len(arguments) in (2, 3):
        return launch_workshop(arguments[1], arguments[2] if len(arguments) == 3 else "", orca)
    raise UsageError(USAGE)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
