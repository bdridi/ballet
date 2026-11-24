"""La capacité d'un harnais (OPP-88) : la part de sa fenêtre de 5 heures et de sa fenêtre de 7 jours déjà consommée.

Maestro ne lance plus de feature quand la fenêtre de 5 h de Claude est presque pleine : elle pourrait s'arrêter en plein vol
(« Claude hit its session limit », en plein Dancer). Ce script ne fait que lire ce chiffre et la config de la sonde ; le Monitor
le compare au seuil (`ballet_monitor.py`), Maestro en tire la décision (`ballet_maestro.py`).

La source est un fichier par harnais, `~/.ballet/capacity/<harnais>.json` (`BALLET_HOME` pour un autre dossier) :

    {"captured_at": "2026-11-24T11:58:00+00:00",
     "windows": {"five_hour": {"used_percent": 42.0, "resets_at": "2026-11-24T15:00:00+00:00"}, "seven_day": {…}}}

Chaque harnais a son fournisseur : le script qui l'écrit. Pour Claude, c'est la statusline de `ballet_statusline.py`, que
`ballet_session.py` branche sur les sessions de Maestro et des Conductors (Claude Code ne donne le chiffre qu'à elle, et
Orca ne le garde dans aucun fichier lisible). Vibe et Grok : pas de fournisseur pour l'instant ; leur fichier n'existe pas,
leur capacité est inconnue.

Un chiffre plus vieux que `stale_after_minutes` est inconnu (`None`) : la statusline ne tourne que dans une session qui
s'affiche, et on ne met jamais en attente sur un vieux chiffre. Pas de fichier, un fichier illisible : inconnu aussi.

La config est la table `[capacity]` du `config.toml` du plugin (les défauts), surchargée clé par clé par celle de
`~/.ballet/maestro.toml` (la machine) :

    five_hour_threshold = 90    le pourcentage UTILISÉ de la fenêtre de 5 h au-delà duquel plus rien de nouveau ne part ; 0 : pas de sonde
    seven_day_threshold = 90    de même pour la fenêtre de 7 jours (Maestro demande alors au Director) ; 0 : pas de sonde
    stale_after_minutes = 30    un chiffre plus vieux est inconnu
"""

import json
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ballet_state

PLUGIN_CONFIG = Path(__file__).resolve().parent.parent / "config.toml"
FIVE_HOUR, SEVEN_DAY = "five_hour", "seven_day"
WINDOWS = (FIVE_HOUR, SEVEN_DAY)
KEYS = ("five_hour_threshold", "seven_day_threshold", "stale_after_minutes")
HYSTERESIS_POINTS = 5   # un seuil franchi à la baisse seulement de cette marge : le chiffre ne fait pas clignoter l'événement


class CapacityError(Exception):
    """La config de la sonde est invalide : le message dit laquelle des clés."""


# --- la lecture ---------------------------------------------------------------


def read(harness, stale_after_minutes, state=None, now=None):
    """Par fenêtre, `{used_percent, resets_at, captured_at}` ; `None` quand la capacité est inconnue (pas de capture, fichier
    illisible, fenêtre absente, chiffre plus vieux que `stale_after_minutes`)."""
    unknown = {window: None for window in WINDOWS}
    captured = _captured(harness, state)
    if not captured:
        return unknown
    at, windows = captured
    if (now or datetime.now(timezone.utc)) - at > timedelta(minutes=stale_after_minutes):
        return unknown
    return {window: _window(windows.get(window), at) for window in WINDOWS}


def _captured(harness, state):
    """(instant de la capture, fenêtres) du fichier du harnais ; rien s'il manque ou s'il est illisible."""
    try:
        content = json.loads(_path(harness, state).read_text(encoding="utf-8"))
        return datetime.fromisoformat(content["captured_at"]), dict(content["windows"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _window(found, captured_at):
    if not isinstance(found, dict) or not isinstance(found.get("used_percent"), (int, float)):
        return None
    return {"used_percent": found["used_percent"], "resets_at": found.get("resets_at", ""),
            "captured_at": captured_at.isoformat()}


# --- le seuil -----------------------------------------------------------------------


def is_above(used_percent, threshold):
    """Le pourcentage est-il au seuil ou au-delà ? Jamais pour un chiffre inconnu (`None`) ni une sonde coupée (seuil 0)."""
    return bool(threshold) and used_percent is not None and used_percent >= threshold


def is_back_under(used_percent, threshold):
    """Une fenêtre franchie est-elle redescendue ? Il faut `HYSTERESIS_POINTS` sous le seuil (au moins sous 1 %) ; un chiffre
    inconnu ou une sonde coupée la lèvent aussi : on ne reste pas en attente sur ce qu'on ne sait plus."""
    return not threshold or used_percent is None or used_percent < max(threshold - HYSTERESIS_POINTS, 1)


# --- l'écriture, par le fournisseur du harnais --------------------------------------


def record(harness, windows, state=None, now=None):
    """Note les fenêtres vues à cet instant (`windows` : fenêtre → `{used_percent, resets_at}`), d'un seul coup : un lecteur
    voit l'ancienne capture ou la nouvelle. Rien à noter, rien d'écrit : l'ancien chiffre vieillit."""
    if not windows:
        return
    at = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    ballet_state.write_atomically(_path(harness, state), json.dumps({"captured_at": at, "windows": windows}, ensure_ascii=False))


def _path(harness, state):
    return ballet_state.state_dir(state) / "capacity" / f"{harness}.json"


# --- la config ----------------------------------------------------------------------


def settings(machine_config):
    """La config de la sonde : les défauts du plugin, surchargés clé par clé par `[capacity]` de la machine (sa config
    `maestro.toml`, déjà lue). Une clé invalide ou inconnue lève `CapacityError`."""
    defaults = tomllib.loads(PLUGIN_CONFIG.read_text(encoding="utf-8")).get("capacity", {})
    merged = {**defaults, **machine_config.get("capacity", {})}
    found = problems(merged)
    if found:
        raise CapacityError("; ".join(found))
    return merged


def problems(table):
    """Ce qui ne va pas dans une table `[capacity]`, en anglais (pour `ballet_config.py check` comme pour `settings`)."""
    found = [f"[capacity] {key} is not a setting (known: {', '.join(KEYS)})" for key in table if key not in KEYS]
    for key in ("five_hour_threshold", "seven_day_threshold"):
        if key in table and not _is_whole_number(table[key], 0, 100):
            found.append(f"[capacity] {key} must be a whole number from 0 to 100 (0: no probe), not {table[key]!r}")
    if "stale_after_minutes" in table and not _is_whole_number(table["stale_after_minutes"], 1, None):
        found.append(f"[capacity] stale_after_minutes must be a whole number, 1 or more, not {table['stale_after_minutes']!r}")
    return found


def _is_whole_number(value, least, most):
    return (isinstance(value, int) and not isinstance(value, bool) and value >= least and (most is None or value <= most))
