"""Le coût d'une Rehearsal ou d'un Workshop : les tokens de ses sessions `claude`, et ce qu'ils vaudraient au prix de l'API.

Claude Code écrit chaque session dans `~/.claude/projects/<dossier>/<session>.jsonl` (le dossier : le chemin où la session a été
lancée, tout caractère hors lettres et chiffres devenu `-`). Chaque réponse y porte son `message.usage` ; une même réponse est
écrite sur plusieurs lignes, on ne garde donc que la dernière par `message.id`. On lit :

- les workers (Dramaturg, Choreographer, Dancer, Critic) : les sessions du dossier de leur worktree, pendant la fenêtre de la
  Rehearsal (les slices d'une feature reprennent le worktree de sa planification : sans fenêtre, elles se partageraient le même
  coût) ; leur rôle est dans le premier message (`You are the Ballet Dancer …`), à défaut la session est nommée par son début
  d'identifiant ;
- le Conductor, lancé depuis le dossier du projet, seulement s'il n'y a pas d'ambiguïté : une seule session du projet dont la
  commande (`/ballet:rehearsal` ou `/ballet:workshop`) porte l'élément, et ses réponses pendant la fenêtre de temps de la
  Rehearsal. Sinon il est laissé de côté, et le rapport le dit.

Le dollar est un équivalent au prix de l'API : le Director est sur un abonnement, dont la vraie limite est le quota. Les tokens
sont donnés en plus, pour cette raison. Les appels annexes de Claude Code (titre de la session, par exemple) ne sont pas
dans les journaux : ils ne sont pas comptés.

Le coût d'un Workshop `assisted` (OPP-95, `kind: workshop-assisted`) voyage dans l'issue : aucune session de Ballet ne le porte, et il peut tourner
dans une session cloud, loin de la base et des journaux du Mac. `of_this_session` mesure la session Claude Code qui
appelle (son journal, trouvé par `CLAUDE_CODE_SESSION_ID`, et ses sous-agents) : la tranche depuis son dernier `publish`
réussi, trouvé dans ce même journal (depuis le début pour le premier), son numéro, et le cumul de la session. Un Workshop
qui publie plusieurs features donne ainsi à chaque issue sa part, sans aucun état gardé. `render_cost_note` en fait le
commentaire de l'issue : une ligne lisible et un bloc caché `<!-- ballet:cost {json} -->` ; `parse_cost_note` le relit pour
la Scène, sans jamais lever : un bloc mal formé rend `None`, et `cost_note_problem` dit pourquoi (`format v2`, `malformed`).

Le module ne lit que les journaux ; il n'écrit rien.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"

# --- les prix : dollars par million de tokens -------------------------------------------------------------------------
# Source : https://platform.claude.com/docs/en/about-claude/pricing (relevée le 2026-11-23, recoupée avec le `costUSD` des journaux).
# Le cache écrit coûte 1,25 × l'entrée pour 5 min, 2 × pour 1 h ; le cache lu, 0,05 × (Haiku : 0,1 ×).
#                      entrée  sortie  cache 5 min  cache 1 h  cache lu
PRICES = {
    "claude-opus-5-5":   (4.00, 20.00, 5.000, 8.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 2.500, 4.00, 0.10),
    "claude-haiku-5-5":  (0.10, 0.50, 0.125, 0.20, 0.01),
}
# Haiku 5.5 : une requête dont le prompt (cache compris) dépasse 100 000 tokens est facturée à ce tarif.
LONG_PROMPT = {"claude-haiku-5-5": (100_000, (0.50, 2.50, 0.625, 1.00, 0.05))}
# Le mode rapide (`usage.speed == "fast"`) double le prix d'Opus 5.5.
FAST_MULTIPLIER = {"claude-opus-5-5": 2}

KINDS = ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read")   # l'ordre des colonnes de PRICES
ROLE_OF_WORKER = re.compile(r"You are the Ballet (\w+)")
PUBLISH_CALL = re.compile(r"\bballet_github\.py\s+publish\b")   # un `publish` lancé par la session, dans son journal
COST_NOTE = re.compile(r"<!--\s*ballet:cost\b(.*?)-->", re.DOTALL)
NOTE_VERSION = 1
NOTE_KINDS = ("workshop-assisted",)   # le Workshop autopilot a son coût dans la base, par sa session de Conductor
NOTE_FIELDS = ("v", "kind", "session", "segment", "from", "to", "tokens", "usd")
COMMAND_OF_CONDUCTOR = re.compile(r"<command-name>/?([\w:-]+)</command-name>\s*<command-args>(.*?)</command-args>", re.DOTALL)


def of_work(worktree, project, command, item, window, projects=None):
    """Le coût d'une Rehearsal ou d'un Workshop : `{rows, total, left_out}`, ou `{missing}` si aucun journal n'est lisible.

    `command` : `ballet:rehearsal` ou `ballet:workshop` ; `item` : l'élément de sa session ; `window` : (début, fin) de la Rehearsal.
    """
    projects = projects or PROJECTS
    worker_rows = _worker_rows(worktree, window, projects)
    conductor_rows, left_out = _conductor_rows(project, command, item, window, projects)
    rows = worker_rows + conductor_rows
    if not rows:
        return {"missing": f"no Claude Code journal activity for {Path(worktree).name} in its time window"}
    return {"rows": rows, "total": _total(rows), "left_out": left_out + _unpriced(rows)}


def line_of(cost):
    """La partie du `done` : `cost ~$8.65 API equivalent (14.6M tokens, 13.1M from cache): Dancer $1.60, …`."""
    if "missing" in cost:
        return f"cost: not available ({cost['missing']})"
    total = cost["total"]
    cached = total["cache_read"]
    summary = f"cost ~${total['usd']:.2f} API equivalent ({_millions(_tokens(total))} tokens, {_millions(cached)} from cache)"
    by_role = ", ".join(f"{role} ${usd:.2f}" for role, usd in _dollars_by_role(cost["rows"]))
    left_out = "".join(f"; {note}" for note in cost.get("left_out", []))
    return f"{summary}: {by_role}{left_out}"


def of_this_session(cwd=None, session_id=None, projects=None, now=None):
    """Le coût de la session Claude Code qui appelle : `{session, segment, from, to, segment_total, session_total, unpriced}`,
    ou `{missing}` quand son journal est introuvable.

    La tranche va du dernier `publish` réussi de la session (ou de son début) jusqu'à maintenant.
    """
    transcript = _current_transcript(cwd, session_id, projects or PROJECTS)
    if transcript is None:
        return {"missing": "the journal of this Claude Code session was not found"}
    messages = _messages_of(transcript) + _subagent_messages_of(transcript.with_suffix(""))
    published = _publish_instants(transcript)
    segment = _after(messages, published[-1] if published else None)
    rows = _rows("Assisted Workshop", segment)
    return {"session": transcript.stem, "segment": len(published) + 1,
            "from": published[-1] if published else _first_instant(messages), "to": now or datetime.now().astimezone(),
            "segment_rows": rows, "segment_total": _total(rows), "session_total": _total(_rows("Assisted Workshop", messages)),
            "unpriced": _unpriced(rows)}


def render_cost_note(measure, kind="workshop-assisted"):
    """Le commentaire de l'issue : une ligne lisible, puis le bloc caché que la Scène relit."""
    note = {"v": NOTE_VERSION, "kind": kind, "session": measure["session"], "segment": measure["segment"],
            "from": _iso(measure["from"]), "to": _iso(measure["to"]), "tokens": _tokens_by_model(measure["segment_rows"]),
            "usd": round(measure["segment_total"]["usd"], 4)}
    return f"{_readable_line(measure)}\n\n<!-- ballet:cost\n{json.dumps(note)}\n-->\n"


def parse_cost_note(text):
    """La note de coût du texte (le premier bloc `ballet:cost`), validée champ par champ ; `None` si elle manque ou est mal
    formée. Ne lève jamais."""
    found = COST_NOTE.search(text if isinstance(text, str) else "")
    if not found:
        return None
    note = _json_object(found.group(1))
    return note if note is not None and _valid_note(note) else None


def cost_note_problem(text):
    """Pourquoi le bloc `ballet:cost` du texte est illisible (`format v2`, `malformed`) ; `None` s'il est lisible ou absent."""
    found = COST_NOTE.search(text if isinstance(text, str) else "")
    if not found or parse_cost_note(text) is not None:
        return None
    version = (_json_object(found.group(1)) or {}).get("v")
    known = isinstance(version, int) and not isinstance(version, bool)
    return f"format v{version}" if known and version != NOTE_VERSION else "malformed"


# --- la session qui appelle -----------------------------------------------------------------------------------------


def _current_transcript(cwd, session_id, projects):
    """Le journal de la session : `<id>.jsonl` dans le dossier du cwd, ou dans n'importe quel dossier (la session a pu
    changer de dossier) ; sans identifiant, le journal le plus récemment écrit du dossier du cwd."""
    session_id = session_id or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    folder = _folder_of(Path(cwd or Path.cwd()), projects)
    if session_id:
        named = [folder / f"{session_id}.jsonl"] + sorted(Path(projects).glob(f"*/{session_id}.jsonl"))
        return next((path for path in named if path.is_file()), None)
    journals = sorted(folder.glob("*.jsonl"), key=lambda path: path.stat().st_mtime) if folder.is_dir() else []
    return journals[-1] if journals else None


def _publish_instants(transcript):
    """Les instants des `publish` de la session qui ont réussi : un appel Bash à `ballet_github.py publish`, dont le résultat
    est arrivé sans erreur (l'appel en cours n'a pas encore de résultat : il n'en est pas un)."""
    calls, instants = set(), []
    for record in _records_of(transcript):
        for block in _content_blocks(record):
            if block.get("type") == "tool_use" and PUBLISH_CALL.search(str((block.get("input") or {}).get("command", ""))):
                calls.add(block.get("id"))
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in calls and not block.get("is_error"):
                instants.append(_instant(record.get("timestamp")))
    return sorted(instant for instant in instants if instant)


def _content_blocks(record):
    content = (record.get("message") or {}).get("content") if isinstance(record.get("message"), dict) else None
    return [block for block in content if isinstance(block, dict)] if isinstance(content, list) else []


def _after(messages, start):
    if start is None:
        return messages
    return [message for message in messages if message["at"] and message["at"] > start]


def _first_instant(messages):
    instants = [message["at"] for message in messages if message["at"]]
    return min(instants) if instants else None


# --- la note de coût ------------------------------------------------------------------------------------------------


def _readable_line(measure):
    segment, session = measure["segment_total"], measure["session_total"]
    line = (f"**Assisted Workshop cost** · this issue: {_millions(_tokens(segment))} tokens · ≈ ${segment['usd']:.2f} (API price) · "
            f"session so far: {_millions(_tokens(session))} tokens · ≈ ${session['usd']:.2f} · segment {measure['segment']}")
    return line + "".join(f" · {note}" for note in measure.get("unpriced", []))


def _tokens_by_model(rows):
    return {row["model"]: {kind: row[kind] for kind in KINDS} for row in rows}


def _iso(instant):
    return instant.isoformat() if instant else ""


def _json_object(text):
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _valid_note(note):
    return (set(NOTE_FIELDS) <= set(note) and note["v"] == NOTE_VERSION and _is_count(note["v"])
            and note["kind"] in NOTE_KINDS and isinstance(note["session"], str) and note["session"]
            and _is_count(note["segment"]) and note["segment"] >= 1
            and _is_instant(note["from"]) and _is_instant(note["to"])
            and _valid_tokens(note["tokens"]) and _is_amount(note["usd"]))


def _valid_tokens(tokens):
    return isinstance(tokens, dict) and all(
        isinstance(model, str) and isinstance(counts, dict) and set(counts) == set(KINDS)
        and all(_is_count(count) for count in counts.values())
        for model, counts in tokens.items())


def _is_count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_amount(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _is_instant(value):
    return isinstance(value, str) and (value == "" or _instant(value) is not None)


# --- les workers ----------------------------------------------------------------------------------------------------


def _worker_rows(worktree, window, projects):
    folder = _folder_of(worktree, projects)
    rows = []
    for session in sorted(folder.glob("*.jsonl")) if folder.is_dir() else []:
        messages = _messages_of(session) + _subagent_messages_of(folder / session.stem)
        rows += _rows(_worker_role(session), _within(messages, window))
    return _merged(rows)


def _worker_role(session):
    """Le rôle dans le premier message du worker ; à défaut, la session."""
    for text in _user_texts(session):
        found = ROLE_OF_WORKER.search(text)
        if found:
            return found.group(1)
    return f"session {session.stem[:8]}"


def _subagent_messages_of(session_folder):
    """Les sous-agents d'une session sont écrits à côté : `<session>/subagents/*.jsonl`."""
    return [message for file in sorted(session_folder.glob("subagents/*.jsonl")) for message in _messages_of(file)]


# --- le Conductor ---------------------------------------------------------------------------------------------------


def _conductor_rows(project, command, item, window, projects):
    """Les lignes du Conductor, et ce qui n'a pas pu l'être (`left_out`)."""
    if not item:
        return [], ["Conductor not counted: its item is not in the state"]
    if not window:
        return [], ["Conductor not counted: no time window"]
    candidates = [session for session in _sessions_of(project, projects) if _plays(session, command, item)]
    if not candidates:
        return [], [f"Conductor not counted: no session of /{command} {item} in the project's journals"]
    in_window = [(session, _within(_messages_of(session), window)) for session in candidates]
    in_window = [(session, messages) for session, messages in in_window if messages]
    if len(in_window) > 1:
        return [], [f"Conductor not counted: {len(in_window)} sessions of /{command} {item} were active in the same window"]
    return _rows("Conductor", [message for _, messages in in_window for message in messages]), []


def _sessions_of(project, projects):
    folder = _folder_of(project, projects)
    return sorted(folder.glob("*.jsonl")) if folder.is_dir() else []


def _plays(session, command, item):
    """La session a été lancée par `/<command> <item>` (premier message utilisateur qui est une commande)."""
    for text in _user_texts(session):
        found = COMMAND_OF_CONDUCTOR.search(text)
        if found:
            return found.group(1) == command and item in found.group(2).split()
    return False


def _within(messages, window):
    """Les réponses de la fenêtre ; sans fenêtre, toutes."""
    if not window:
        return messages
    start, end = window
    return [message for message in messages if message["at"] and start <= message["at"] <= end]


# --- la lecture des journaux ----------------------------------------------------------------------------------------


def _folder_of(path, projects):
    return Path(projects) / re.sub(r"[^A-Za-z0-9]", "-", str(path))


def _records_of(session):
    try:
        lines = Path(session).read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for text in lines:
        try:
            yield json.loads(text)
        except ValueError:
            continue


def _user_texts(session):
    for record in _records_of(session):
        if record.get("type") != "user":
            continue
        content = record.get("message", {}).get("content")
        if isinstance(content, str):
            yield content
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "text":
                yield block.get("text", "")


def _messages_of(session):
    """Les réponses de la session, dédoublonnées par `message.id` (la dernière ligne d'une réponse a son usage final)."""
    answers = {}
    for record in _records_of(session):
        message = record.get("message")
        if record.get("type") == "assistant" and isinstance(message, dict) and message.get("usage") and message.get("id") \
                and not str(message.get("model", "")).startswith("<"):   # `<synthetic>` : une réponse écrite par Claude Code, sans appel
            answers[message["id"]] = {"id": message["id"], "model": message.get("model", ""), "usage": message["usage"],
                                      "at": _instant(record.get("timestamp"))}
    return list(answers.values())


def _instant(text):
    try:
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


# --- les chiffres ---------------------------------------------------------------------------------------------------


def _rows(role, messages):
    """Une ligne par modèle : ses tokens et leur équivalent en dollars."""
    rows = {}
    for message in messages:
        tokens = _tokens_of(message["usage"])
        row = rows.setdefault(message["model"], {"role": role, "model": message["model"], **dict.fromkeys(KINDS, 0), "usd": 0.0})
        for kind in KINDS:
            row[kind] += tokens[kind]
        row["usd"] += _dollars(message["model"], tokens, message["usage"].get("speed"))
    return list(rows.values())


def _tokens_of(usage):
    written = usage.get("cache_creation") or {}
    one_hour = written.get("ephemeral_1h_input_tokens", 0)
    five_minutes = written.get("ephemeral_5m_input_tokens", usage.get("cache_creation_input_tokens", 0) - one_hour)
    return {"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0), "cache_write_5m": five_minutes,
            "cache_write_1h": one_hour, "cache_read": usage.get("cache_read_input_tokens", 0)}


def _dollars(model, tokens, speed):
    prices = _prices_of(model, tokens)
    if prices is None:
        return 0.0
    dollars = sum(tokens[kind] * price for kind, price in zip(KINDS, prices)) / 1_000_000
    return dollars * (FAST_MULTIPLIER.get(model, 1) if speed == "fast" else 1)


def _prices_of(model, tokens):
    long_prompt = LONG_PROMPT.get(model)
    prompt = tokens["input"] + tokens["cache_read"] + tokens["cache_write_5m"] + tokens["cache_write_1h"]
    if long_prompt and prompt > long_prompt[0]:
        return long_prompt[1]
    return PRICES.get(model)


def _unpriced(rows):
    models = sorted({row["model"] for row in rows if row["model"] not in PRICES})
    return [f"model without a price, counted as $0: {model}" for model in models]


def _merged(rows):
    """Plusieurs sessions d'un même rôle (un Dancer repris à neuf, par exemple) ne font qu'une ligne par modèle."""
    merged = {}
    for row in rows:
        key = (row["role"], row["model"])
        into = merged.setdefault(key, {**row, **dict.fromkeys(KINDS, 0), "usd": 0.0})
        for kind in KINDS:
            into[kind] += row[kind]
        into["usd"] += row["usd"]
    return list(merged.values())


def _total(rows):
    total = {kind: sum(row[kind] for row in rows) for kind in KINDS}
    total["usd"] = sum(row["usd"] for row in rows)
    return total


def _tokens(counts):
    return sum(counts[kind] for kind in KINDS)


def _dollars_by_role(rows):
    by_role = {}
    for row in rows:
        by_role[row["role"]] = by_role.get(row["role"], 0.0) + row["usd"]
    return by_role.items()


def _millions(count):
    return f"{count / 1_000_000:.1f}M" if count >= 100_000 else f"{count / 1000:.0f}k"
