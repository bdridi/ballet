"""Applique une nouvelle version de Ballet sur la machine, d'un seul coup (`/ballet:setup upgrade`).

    python3 <clone>/scripts/ballet_upgrade.py

À lancer depuis le clone, après un `git pull` (ou une nouvelle version écrite dans le clone). Dans l'ordre :

1. le Monitor et la session Maestro s'arrêtent : leurs terminaux Orca sont fermés (et l'attente de Maestro arrêtée, un
   redémarrage en cours aussi). Un Monitor ou un Maestro qui tourne garde le code avec lequel il est parti ; l'arrêter
   d'abord l'empêche aussi de réécrire un ancien fichier d'état pendant la reprise ;
2. le plugin est réinstallé depuis le clone, pour chaque CLI (`reset_plugin.py`) ;
3. l'état d'une version plus ancienne est repris dans la base (`ballet_legacy.py import`), s'il en reste ;
4. le bail est levé, puis la boîte est vérifiée (recréée seulement si son terminal a disparu), un nouveau Monitor et une
   nouvelle session Maestro démarrent dans leurs terminaux. La nouvelle session prend le bail et ouvre par
   « While you were away » : rien de la boîte n'est perdu.

Les Conductors qui tournent ne sont pas touchés : chacun de leurs appels lance les scripts réinstallés. Les terminaux
sont retrouvés dans la base, ou dans un ancien `maestro.toml` quand l'état n'a pas encore été repris.

Sort avec 0 quand tout est fait, 1 si une étape a échoué (les suivantes sont quand même tentées quand elles ont un sens,
et chacune est dite).
"""

import os
import sys
from pathlib import Path

import ballet_db
import ballet_legacy
import ballet_maestro
import ballet_runtime
import reset_plugin
from ballet_maestro import MaestroError

CLONE = Path(__file__).resolve().parent.parent
FAILED = "✗"


def upgrade(orca, state=None, reinstall=None):
    """Arrête le Monitor et Maestro, réinstalle le plugin, reprend l'ancien état, puis redémarre le tout. Rend le bilan."""
    report = []
    noted = _noted_terminals(state)
    _refuse_from_a_terminal_it_closes(noted)
    _step(report, "stop the Monitor", lambda: _close("Monitor", noted["monitor_terminal"], orca))
    _step(report, "stop Maestro", lambda: _stop_maestro(noted, orca))
    _step(report, "reinstall the plugin", lambda: (reinstall or _reinstall)())
    _step(report, "take over the older state", lambda: _take_over(state))
    _step(report, "release the lease", lambda: _release(state))
    _step(report, "check the mailbox", lambda: ballet_maestro.mailbox(orca, state))
    _step(report, "start the Monitor", lambda: ballet_maestro.monitor(orca, state))
    _step(report, "start Maestro", lambda: ballet_maestro.maestro(orca, state))
    return report


# --- les étapes ---------------------------------------------------------------


def _refuse_from_a_terminal_it_closes(noted):
    """Lancé depuis le terminal de Maestro (ou du Monitor), l'upgrade se fermerait lui-même en route : rien n'est fait."""
    here = os.environ.get("ORCA_TERMINAL_HANDLE", "")
    if here and here in (noted["maestro_terminal"], noted["monitor_terminal"]):
        raise MaestroError(f"this runs in terminal {here}, which the upgrade closes: run /ballet:setup upgrade from another "
                           "session (not Maestro's)")


def _noted_terminals(state):
    """Les terminaux et le pid de l'attente : ceux de la base, sinon ceux d'un ancien `maestro.toml`."""
    noted = {**ballet_runtime.read(state)}
    for name, value in ballet_legacy.old_runtime(state).items():
        noted[name] = noted.get(name) or value
    return noted


def _close(what, handle, orca):
    """Ferme le terminal s'il vit encore ; rien noté, ou déjà fermé, c'est dit."""
    if not handle:
        return f"no {what} terminal noted"
    if handle not in ballet_maestro.live_terminals(orca):
        return f"{what} terminal {handle} was already closed"
    orca(["terminal", "close", "--terminal", handle, "--json"])
    return f"{what} stopped: terminal {handle} closed"


def _stop_maestro(noted, orca):
    """L'attente de Maestro, puis son terminal, et un redémarrage en cours s'il y en a un."""
    ballet_maestro.stop_the_wait(noted["lease_pid"])
    lines = [_close("Maestro", noted["maestro_terminal"], orca)]
    if noted["restart_terminal"]:
        lines.append(_close("restart", noted["restart_terminal"], orca))
    return "; ".join(lines)


def _reinstall():
    lines = reset_plugin.reset_plugin(CLONE)
    if not lines:
        raise MaestroError("no CLI found (claude, vibe, grok)")
    if any(line.startswith(FAILED) for line in lines):
        raise MaestroError("; ".join(lines))
    return "; ".join(lines)


def _take_over(state):
    taken = ballet_legacy.run_import(state)
    return "taken over: " + ", ".join(str(path) for path in taken) if taken else "nothing to take over"


def _release(state):
    """Le bail de l'ancienne session est levé, et la pause de son redémarrage interrompu retirée : la nouvelle part propre."""
    runtime = ballet_runtime.read(state)
    ballet_maestro.release_lease(state)
    if runtime["restart_terminal"]:
        if runtime["restart_owns_pause"]:
            ballet_maestro.resume(state)
        ballet_runtime.update(state, restart_terminal="", restart_owns_pause=False)
    return "lease released: the new Maestro session takes it"


def _step(report, label, action):
    """Une étape, dite sur sa ligne ; une panne n'arrête pas les suivantes."""
    try:
        report.append(f"✓ {label}: {action()}")
    except (MaestroError, *ballet_db.ERRORS, OSError) as error:
        report.append(f"{FAILED} {label}: {error}")


# --- ligne de commande --------------------------------------------------------


def main(argv, orca=None):
    if argv[1:]:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    try:
        report = upgrade(orca or ballet_maestro.run_orca)
    except MaestroError as error:
        print(f"upgrade: {error}", file=sys.stderr)
        return 1
    print("\n".join(report))
    return 1 if any(line.startswith(FAILED) for line in report) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
