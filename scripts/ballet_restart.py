"""Le redémarrage de Maestro (OPP-02, étape 5) : sa session vide son contexte quand plus aucun Conductor ne travaille.

    python3 ballet_restart.py when-idle --owner <jeton>   # la demande, par la session Maestro (le jeton de son bail)
    python3 ballet_restart.py run                         # l'exécution, dans son terminal Orca `maestro-restart`

La session Maestro demande, puis continue de relayer. `when-idle` pose le drapeau `auto_launch_paused` (plus rien ne part
seul), crée le terminal `maestro-restart` et rend la main. Ce terminal, à part de celui de Maestro, survit à sa fermeture :
`run` y attend le bon moment, remplace la session, puis retire le drapeau (s'il l'a posé) et se ferme.

Le bon moment : aucun Conductor ne travaille *et* la session Maestro dort sur sa boîte (son attente tourne : elle ne porte
pas une réponse à un Conductor). Un Conductor travaille quand sa ligne du registre est `running`, que son terminal vit
dans Orca et que sa Rehearsal en cours, ou son Workshop, n'est pas `escalated` : une pause sur escalade (un plan en
review compris) ne compte pas. Le registre seul ne suffit pas : après un `tell`, son dernier événement reste `escalate`
alors que le Conductor a repris. Sans session Maestro vivante, le bon moment est tout de suite.

Le remplacement : le bail est levé, le terminal `maestro` fermé, puis `ballet_maestro.py maestro` en crée un nouveau, où
la session prend le bail (`claim`), lit `recap` et ouvre par « While you were away ». Sans silence au bout de
`MAX_WAIT_SECONDS`, ou si la nouvelle session ne prend pas le bail dans `CLAIM_WAIT_SECONDS`, le script abandonne : il lève
le drapeau qu'il a posé et le dit dans la boîte (`maestro · restart abandoned`).

Une session Maestro ouverte à la main, hors du terminal `maestro` de `maestro.toml`, ne peut pas être redémarrée par
script : la demande est refusée (`/clear`, puis `claim --take-over`).
"""

import json
import os
import shlex
import sys
import time
from pathlib import Path

import ballet_conductors
import ballet_maestro
import ballet_state
from ballet_maestro import MaestroError

RESTART_TITLE = "maestro-restart"
RESTART_SCRIPT = Path(__file__).resolve()
POLL_SECONDS = 30
MAX_WAIT_SECONDS = 4 * 3600
CLAIM_POLL_SECONDS = 5
CLAIM_WAIT_SECONDS = 300
ABANDONED_SUBJECT = "maestro · restart abandoned"
USAGE = "usage: when-idle --owner <token> | run"


class UsageError(Exception):
    pass


# --- la demande ---------------------------------------------------------------


def request(owner, orca, state=None):
    """Pose le drapeau de pause, crée le terminal qui attendra le bon moment, et rend la main. Refusée quand le jeton ne tient
    pas le bail, quand la session ne tourne pas dans le terminal de Maestro, ou quand un redémarrage est déjà en cours."""
    ballet_maestro.confirm_owner(owner, state)
    with ballet_state.locked(state):
        config = ballet_maestro.read_config(state)
        _refuse_unless_maestro_terminal(config, orca)
        pending = config.get("restart", {}).get("terminal", "")
        if pending and pending in ballet_maestro.live_terminals(orca):
            return f"restart already in progress: terminal {pending}"
        paused_by_us = not ballet_maestro.is_paused(state)
        ballet_maestro.pause(state)
        try:
            terminal = _create_restart_terminal(orca)
        except MaestroError:
            _lift_pause(paused_by_us, state)
            raise
        config["restart"] = {"terminal": terminal, "paused": paused_by_us}
        ballet_maestro.write_config(config, state)
    return (f"restart scheduled: terminal {terminal} waits until no Conductor is working and this session sleeps on its mailbox, "
            "then restarts it; auto launch is paused until then. Keep relaying meanwhile")


def _refuse_unless_maestro_terminal(config, orca):
    handle = config.get("maestro", {}).get("terminal", "")
    if not handle or handle not in ballet_maestro.live_terminals(orca):
        raise MaestroError(f"this session does not run in the terminal Maestro owns ({ballet_maestro.CONFIG_NAME} [maestro]): "
                           "a script cannot restart it; clear it by hand (/clear), then claim --take-over on the Director's yes")


def _create_restart_terminal(orca):
    receipt = json.loads(orca(["terminal", "create", "--title", RESTART_TITLE, "--command", _restart_command(), "--json"]))
    return ballet_maestro.first_id(receipt, "term_", "orca terminal create")


def _restart_command():
    """`python3 <clone>/scripts/ballet_restart.py run`, avec `BALLET_HOME` quand il est posé : il lit le même dossier d'état."""
    home = os.environ.get("BALLET_HOME")
    return " ".join([*([f"BALLET_HOME={shlex.quote(home)}"] if home else []), "python3", shlex.quote(str(RESTART_SCRIPT)), "run"])


# --- qui travaille ------------------------------------------------------------


def working(orca, state=None):
    """Les Conductors qui travaillent, `<projet>#<élément>`, triés. Une Orca injoignable lève : on ne dit jamais « personne »
    à l'aveugle."""
    config = ballet_maestro.read_config(state)
    alive = ballet_maestro.live_terminals(orca)
    return sorted(key for key, line in ballet_conductors.read(state).items()
                  if _is_running(line, alive) and not _paused_on_escalation(line, config))


def _is_running(line, alive):
    return ballet_conductors.state_of(line) == ballet_conductors.RUNNING and line["terminal"] in alive


def _paused_on_escalation(line, config):
    """Sa Rehearsal en cours, ou son Workshop, attend le Director. Sans session encore (lancé à l'instant), il travaille."""
    project = config["projects"].get(line["project"])
    if not project:
        return False
    sessions = ballet_maestro.sessions_of(Path(project["path"]))
    return any(state == "escalated" for item, _, state in sessions if item.lstrip("#") == line["item"])


# --- l'exécution --------------------------------------------------------------


def run(orca, state=None, sleep=time.sleep, clock=time.monotonic):
    """Attend le bon moment, remplace la session Maestro, attend que la nouvelle prenne le bail, puis range tout."""
    deadline = clock() + MAX_WAIT_SECONDS
    while not _idle(orca, state):
        if clock() >= deadline:
            return _finish(orca, state, f"{_names_working(orca, state)} still working after {MAX_WAIT_SECONDS // 3600} h: Maestro left as it is")
        sleep(POLL_SECONDS)
    _replace_maestro(orca, state)
    if not _new_session_claims(state, sleep, clock):
        return _finish(orca, state, f"the new Maestro session did not claim the lease in {CLAIM_WAIT_SECONDS // 60} min: "
                                    "open /ballet:maestro by hand")
    return _finish(orca, state, "")


def _idle(orca, state):
    """Aucun Conductor ne travaille et la session Maestro dort sur sa boîte. Une Orca qui ne répond pas : pas encore."""
    try:
        return not working(orca, state) and not ballet_maestro.is_busy(state)
    except MaestroError:
        return False


def _names_working(orca, state):
    try:
        return ", ".join(working(orca, state)) or "a session"
    except MaestroError:
        return "a Conductor"


def _replace_maestro(orca, state):
    old = ballet_maestro.read_config(state).get("maestro", {}).get("terminal", "")
    ballet_maestro.release_lease(state)
    if old and old in ballet_maestro.live_terminals(orca):
        orca(["terminal", "close", "--terminal", old, "--json"])
    ballet_maestro.maestro(orca, state)


def _new_session_claims(state, sleep, clock):
    deadline = clock() + CLAIM_WAIT_SECONDS
    while not ballet_maestro.read_config(state)["lease"]["owner"]:
        if clock() >= deadline:
            return False
        sleep(CLAIM_POLL_SECONDS)
    return True


def _finish(orca, state, problem):
    """Retire le drapeau s'il est à nous, oublie la demande, dit l'abandon dans la boîte, puis ferme ce terminal."""
    config = ballet_maestro.read_config(state)
    _lift_pause(config.get("restart", {}).get("paused", False), state)
    if config.pop("restart", None) is not None:
        ballet_maestro.write_config(config, state)
    if problem:
        _tell_the_mailbox(problem, orca, state)
    _close_this_terminal(orca)
    return f"restart abandoned: {problem}" if problem else "Maestro restarted: a new session took the lease"


def _lift_pause(paused_by_us, state):
    if paused_by_us:
        ballet_maestro.resume(state)


def _tell_the_mailbox(problem, orca, state):
    try:
        ballet_maestro.post_status(ballet_maestro.mailbox_run(state), ABANDONED_SUBJECT, f"Restart of Maestro abandoned: {problem}.",
                                   "high", orca)
    except MaestroError as error:
        print(f"restart: Maestro not told: {error}", file=sys.stderr)


def _close_this_terminal(orca):
    handle = os.environ.get("ORCA_TERMINAL_HANDLE")
    if handle:
        orca(["terminal", "close", "--terminal", handle, "--json"])


# --- ligne de commande --------------------------------------------------------


def main(argv, orca=None):
    """Affiche le résultat et sort avec 0 ; 1 si le redémarrage est refusé, 2 sur un usage invalide."""
    try:
        print(_command(argv[1:], orca or ballet_maestro.run_orca))
    except UsageError as error:
        print(error, file=sys.stderr)
        return 2
    except (MaestroError, OSError) as error:
        print(f"restart: {error}", file=sys.stderr)
        return 1
    return 0


def _command(arguments, orca):
    if arguments[:2] == ["when-idle", "--owner"] and len(arguments) == 3:
        return request(arguments[2], orca)
    if arguments == ["run"]:
        return run(orca)
    raise UsageError(USAGE)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
