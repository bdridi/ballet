"""Les frictions d'une Rehearsal ou d'un Workshop : ce qui a coincé, coûté un tour de plus ou tourné en rond.

Calculées sans LLM à la fin de la Rehearsal (ou du Workshop), à partir de son état et de ses entrées du journal
(`.ballet/run/journal.jsonl`), puis gardées dans son état (`frictions`) et dans le journal (événement `frictions`) :
la Scène les montre, et le `done` de la session les donne à Maestro. Chaque friction :

    kind    escalation | rejections | red_proofs | red_mutations | refused_reports | nudges | policy | diff
    count   combien de fois
    text    la ligne lisible, en anglais (les agents la lisent)

Le module ne lit et n'écrit rien lui-même : on lui passe l'état et les entrées du journal.
"""

from datetime import datetime

ESCALATION_TEXT_LIMIT = 200


def of_rehearsal(state, entries):
    """Les frictions d'une Rehearsal finie, et sa durée."""
    frictions = _escalations(entries)
    frictions += _counted("rejections", state.get("round_trips", 0), "Critic rejection")
    frictions += _counted("red_proofs", state.get("red_proofs", 0), "red proof")
    frictions += _counted("red_mutations", state.get("red_mutations", 0), "red mutation")
    frictions += _counted("refused_reports", state.get("refused_reports", 0), "Dancer report refused", plural="Dancer reports refused")
    frictions += _nudges(entries)
    frictions += _policy(state.get("violations", {}))
    frictions += _oversized(state.get("size", {}))
    return {"seconds": _seconds(entries), "frictions": frictions}


def of_workshop(state, entries):
    """Les frictions d'un Workshop fini, et sa durée."""
    frictions = _escalations(entries)
    frictions += _counted("refused_reports", state.get("refused_reports", 0), "Dramaturg report refused", plural="Dramaturg reports refused")
    frictions += _nudges(entries)
    frictions += _policy({"dramaturg": state.get("violations", 0)})
    return {"seconds": _seconds(entries), "frictions": frictions}


def line(name, record):
    """Une ligne pour le `done` : `frictions of FEAT-007 (42 min): escalated: …; 1 red proof`, ou `…: none`."""
    listed = "; ".join(friction["text"] for friction in record.get("frictions", [])) or "none"
    return f"frictions of {name} ({_duration(record.get('seconds', 0))}): {listed}"


# --- détails ------------------------------------------------------------------


def _escalations(entries):
    reasons = [entry.get("detail", {}).get("reason", "") for entry in entries if entry.get("event") == "escalate"]
    return [{"kind": "escalation", "count": 1, "text": f"escalated: {_shortened(reason)}"} for reason in reasons]


def _counted(kind, count, singular, plural=None):
    if not count:
        return []
    name = singular if count == 1 else (plural or f"{singular}s")
    return [{"kind": kind, "count": count, "text": f"{count} {name}"}]


def _nudges(entries):
    count = sum(1 for entry in entries if entry.get("event") == "handoff" and entry.get("detail", {}).get("how") == "nudge")
    return _counted("nudges", count, "worker reminded to send its worker_done", plural="workers reminded to send their worker_done")


def _policy(violations):
    broken = {role: count for role, count in violations.items() if count}
    if not broken:
        return []
    listed = ", ".join(f"{role} ×{count}" for role, count in sorted(broken.items()))
    return [{"kind": "policy", "count": sum(broken.values()), "text": f"policy refused: {listed}"}]


def _oversized(size):
    if not size.get("over"):
        return []
    return [{"kind": "diff", "count": 1, "text": f"diff {size['counted']} lines over the {size['limit']} limit"}]


def _seconds(entries):
    """Du premier `begin` à la dernière entrée du journal."""
    stamps = [datetime.fromisoformat(entry["at"]) for entry in entries if entry.get("at")]
    begins = [datetime.fromisoformat(entry["at"]) for entry in entries if entry.get("event") == "begin" and entry.get("at")]
    if not stamps:
        return 0
    return max(0, round((max(stamps) - (min(begins) if begins else min(stamps))).total_seconds()))


def _duration(seconds):
    minutes = round(seconds / 60)
    return f"{minutes} min" if minutes < 120 else f"{minutes // 60} h {minutes % 60:02d}"


def _shortened(text):
    text = " ".join(text.split())
    return text if len(text) <= ESCALATION_TEXT_LIMIT else text[:ESCALATION_TEXT_LIMIT - 1] + "…"
