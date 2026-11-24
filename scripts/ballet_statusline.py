"""La statusline de Ballet pour Claude Code (OPP-88) : le fournisseur de capacité de Claude (`ballet_capacity.py`).

    claude --settings '{"statusLine": {"type": "command", "command": "python3 …/ballet_statusline.py"}}'

Claude Code envoie à sa statusline, sur l'entrée standard, un JSON dont `rate_limits` dit la part consommée des fenêtres de
5 heures et de 7 jours : `{"five_hour": {"used_percentage": 0-100, "resets_at": <epoch>}, "seven_day": {…}}` (aussi des
variantes par modèle, que Ballet laisse ; la forme OAuth dit `utilization`). `rate_limits` est `null` avec une clé d'API,
Bedrock ou Vertex : rien n'est noté, la capacité reste inconnue. Aucune autre voie ne donne ce chiffre.

Cette commande note ces fenêtres (`ballet_capacity.record`), puis rend une ligne courte (`5h 94% · 7d 12%`). Elle ne lève
jamais et sort toujours avec 0 : une statusline cassée ne doit jamais gêner une session.

`--settings` remplace la `statusLine` de l'utilisateur (une seule commande par session) : celle de l'utilisateur, lue dans ses
réglages (`$CLAUDE_CONFIG_DIR/settings.json`, sinon `~/.claude/settings.json`), est donc lancée à la suite avec la même entrée,
et c'est son affichage qui est rendu (la statusline d'Orca continue ainsi de poster ses chiffres à Orca). Si elle échoue ou
n'existe pas, la ligne de Ballet reste.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import ballet_capacity

HARNESS = "claude"
CHAIN_TIMEOUT_SECONDS = 5
MILLISECONDS_FROM = 1e10   # un instant au-delà est en millisecondes (la lecture qu'Orca fait aussi du même champ)


def main(argv, stdin=None, stdout=None, state=None, config_dir=None):
    """Lit l'entrée standard, écrit la ligne de la statusline ; sort toujours avec 0."""
    try:
        line = run((stdin or sys.stdin).read(), state, config_dir)
    except Exception:  # une statusline ne doit jamais faire d'erreur : pas de ligne plutôt qu'une trace
        line = ""
    print(line, file=stdout or sys.stdout)
    return 0


def run(payload, state=None, config_dir=None):
    """Note les fenêtres du JSON de Claude Code, puis rend l'affichage de la statusline de l'utilisateur, ou à défaut une
    ligne courte de Ballet."""
    windows = windows_of(_rate_limits_in(payload))
    _note(windows, state)
    return _users_statusline(payload, config_dir) or _short_line(windows)


def windows_of(rate_limits):
    """Fenêtre → `{used_percent, resets_at}` pour les fenêtres de 5 h et de 7 jours que Claude Code donne ; vide sans
    `rate_limits` (une clé d'API) ou sans pourcentage lisible."""
    if not isinstance(rate_limits, dict):
        return {}
    found = {window: _window(rate_limits.get(window)) for window in ballet_capacity.WINDOWS}
    return {window: values for window, values in found.items() if values}


def _window(raw):
    if not isinstance(raw, dict):
        return None
    used = raw.get("used_percentage", raw.get("utilization"))
    if isinstance(used, bool) or not isinstance(used, (int, float)):
        return None
    return {"used_percent": float(min(100, max(0, used))), "resets_at": _date_of(raw.get("resets_at"))}


def _date_of(moment):
    """L'instant de reset en date ISO UTC ; vide quand il n'est ni un nombre (secondes ou millisecondes) ni une date."""
    try:
        if isinstance(moment, str) and not moment.strip().replace(".", "", 1).isdigit():
            return datetime.fromisoformat(moment.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        seconds = float(moment)
        return datetime.fromtimestamp(seconds / 1000 if seconds > MILLISECONDS_FROM else seconds, timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _rate_limits_in(payload):
    try:
        found = json.loads(payload)
    except ValueError:
        return None
    return found.get("rate_limits") if isinstance(found, dict) else None


def _note(windows, state):
    try:
        ballet_capacity.record(HARNESS, windows, state)
    except OSError:   # un dossier d'état illisible ne coûte que ce chiffre : la statusline continue
        pass


def _short_line(windows):
    labels = {ballet_capacity.FIVE_HOUR: "5h", ballet_capacity.SEVEN_DAY: "7d"}
    return " · ".join(f"{labels[window]} {round(values['used_percent'])}%" for window, values in windows.items())


# --- la statusline de l'utilisateur, chaînée --------------------------------------------


def _users_statusline(payload, config_dir):
    """L'affichage de la commande de statusline des réglages de l'utilisateur, lancée avec la même entrée ; vide quand il
    n'en a pas, quand c'est celle de Ballet elle-même, ou quand elle échoue."""
    command = _users_command(config_dir)
    if not command or Path(__file__).name in command:
        return ""
    try:
        done = subprocess.run(command, shell=True, input=payload, capture_output=True, text=True, timeout=CHAIN_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.rstrip("\n") if done.returncode == 0 else ""


def _users_command(config_dir):
    folder = Path(config_dir or os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    try:
        status_line = json.loads((folder / "settings.json").read_text(encoding="utf-8")).get("statusLine")
    except (OSError, ValueError, AttributeError):
        return ""
    if isinstance(status_line, dict) and status_line.get("type") == "command" and isinstance(status_line.get("command"), str):
        return status_line["command"]
    return ""


if __name__ == "__main__":
    sys.exit(main(sys.argv))
