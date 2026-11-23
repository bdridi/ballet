"""Le format unique des messages entre rôles (`templates/message.md`) : lecture et vérification.

    python3 ballet_message.py check <message.md>   # affiche l'en-tête, ou ce qui ne va pas

Première ligne : l'en-tête, une ligne de JSON. Puis une ligne vide et le corps en Markdown.
"""

import json
import re
import sys
from pathlib import Path

PEOPLE = ("dramaturg", "choreographer", "dancer", "critic", "conductor", "director")
TYPES = ("question", "answer", "report", "verdict", "escalation", "revise", "approve")
VERDICT_LINE = re.compile(r"^VERDICT: (APPROVED|REJECTED|ESCALATE)$", re.MULTILINE)


class MessageError(Exception):
    """Le message ne suit pas `templates/message.md`."""


def read_message(path):
    """Renvoie l'en-tête vérifié et le texte entier du message."""
    return parse_message(_read(path))


def parse_message(text):
    """Comme `read_message`, pour un message déjà en main (lu chez Orca)."""
    header = _parse_header(text.split("\n", 1)[0])
    _check_header(header)
    if header["type"] == "verdict":
        verdict_of(text)
    return header, text


def verdict_of(text):
    match = VERDICT_LINE.search(text)
    if not match:
        raise MessageError("a verdict needs a `VERDICT: APPROVED|REJECTED|ESCALATE` line")
    return match.group(1)


def notes_of(text):
    """Les notes d'un verdict : les points de sa section `## Notes` (« none » n'en est pas une)."""
    section = re.search(r"^## Notes[ \t]*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if not section:
        return []
    items = [item.strip() for item in re.findall(r"^(?:-|\d+\.)\s+(.+)$", section.group(1), re.MULTILINE)]
    return [item for item in items if item.strip(" .*_").lower() != "none"]


def main(argv):
    if len(argv) != 3 or argv[1] != "check":
        print("usage: ballet_message.py check <message.md>", file=sys.stderr)
        return 2
    try:
        header, _ = read_message(argv[2])
    except MessageError as error:
        print(f"invalid message: {error}", file=sys.stderr)
        return 1
    print(json.dumps(header, ensure_ascii=False))
    return 0


# --- détails ----------------------------------------------------------------


def _read(path):
    path = Path(path)
    if not path.is_file():
        raise MessageError(f"file not found: {path}")
    return path.read_text(encoding="utf-8")


def _parse_header(first_line):
    try:
        header = json.loads(first_line)
    except json.JSONDecodeError:
        header = None
    if not isinstance(header, dict) or header.get("ballet") != "message":
        raise MessageError("the first line is not a Ballet message header (see templates/message.md)")
    return header


def _check_header(header):
    for key, allowed in (("from", PEOPLE), ("to", PEOPLE), ("type", TYPES)):
        if header.get(key) not in allowed:
            raise MessageError(f"header `{key}` must be one of: {', '.join(allowed)}")
    if not isinstance(header.get("subject"), str) or not header["subject"].strip():
        raise MessageError("header `subject` must be a non-empty string")
    if not isinstance(header.get("round"), int) or isinstance(header["round"], bool) or header["round"] < 1:
        raise MessageError("header `round` must be an integer, 1 or more")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
