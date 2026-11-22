"""La taille du contexte d'une session Claude Code, lue dans son transcript (OPP-78, spike 0003).

    <claude>/projects/<dossier du projet>/<id de session>.jsonl

`<claude>` est `CLAUDE_CONFIG_DIR` quand il est posé, sinon `~/.claude`. Le transcript est cherché par l'id de session, dans
tous les dossiers de projets : plusieurs sessions partagent le dossier de Maestro, seul l'id les distingue.

Le contexte courant est la somme des trois entrées (`input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`)
du `usage` du dernier message de l'assistant : la sortie du message n'y est pas, elle entre dans l'entrée de l'appel suivant.
Sont ignorés : les messages `<synthetic>` à usage nul (une interruption, une erreur), ceux d'un sous-agent, et une dernière
ligne coupée par une écriture en cours. Une compaction n'a rien de spécial : le message suivant donne simplement un chiffre
plus bas. La fenêtre du modèle ne se lit pas ici : le transcript ne la dit pas (c'est `[maestro] context_window_tokens`).

Ce module ne fait que lire : il n'écrit jamais dans le dossier de Claude.
"""

import json
import os
import re
from pathlib import Path

INPUT_FIELDS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
SYNTHETIC_MODEL = "<synthetic>"
SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def claude_home():
    """Le dossier de Claude Code : `CLAUDE_CONFIG_DIR`, sinon `~/.claude`."""
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def transcript_of(session_id):
    """Le transcript de la session, ou `None` quand il n'existe pas (ou que l'id n'en est pas un)."""
    if not SESSION_ID.match(session_id):
        return None
    return next(iter(claude_home().glob(f"projects/*/{session_id}.jsonl")), None)


def used_tokens(transcript):
    """Le contexte courant en tokens, d'après le dernier message de l'assistant ; `None` tant qu'il n'y en a pas."""
    used = None
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        found = _context_of(line)
        if found:
            used = found
    return used


def _context_of(line):
    """Le contexte que cette ligne annonce ; 0 quand ce n'est pas un message de l'assistant à compter."""
    if '"assistant"' not in line:
        return 0
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:   # la dernière ligne, coupée pendant l'écriture
        return 0
    if not isinstance(entry, dict) or entry.get("type") != "assistant" or entry.get("isSidechain"):
        return 0
    message = entry.get("message") or {}
    if message.get("model") == SYNTHETIC_MODEL:
        return 0
    usage = message.get("usage") or {}
    return sum(usage.get(field, 0) for field in INPUT_FIELDS)
