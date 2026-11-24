"""Les frictions d'une Rehearsal ou d'un Workshop : ce qui a coincé, coûté un tour de plus ou tourné en rond.

Calculées sans LLM à la fin de la Rehearsal (ou du Workshop), à partir de son état et de ses entrées du journal
(le journal de la base, `ballet_store.journal_of`), puis gardées dans son état (`frictions`) et dans le journal (événement `frictions`) :
la Scène les montre, et le `done` de la session les donne à Maestro. Chaque friction :

    kind    escalation | rejections | red_proofs | red_mutations | refused_reports | nudges | idle | policy | diff
    count   combien de fois
    text    la ligne lisible, en anglais (les agents la lisent)

À côté des frictions, le coût (`cost`, de `ballet_cost`) : les tokens des sessions du worktree et du Conductor, et leur équivalent
au prix de l'API. Des journaux illisibles ne font jamais échouer la fin : le coût est dit absent.

Le module ne lit et n'écrit rien lui-même : on lui passe l'état et les entrées du journal.
"""

from datetime import datetime

import ballet_cost

ESCALATION_TEXT_LIMIT = 200


def of_rehearsal(state, entries):
    """Les frictions d'une Rehearsal finie, et sa durée."""
    frictions = rehearsal_frictions(state, entries)
    cost = _cost_of(state, entries, command="ballet:rehearsal", item=state.get("session", ""))
    return {"seconds": _seconds(entries), "frictions": frictions, "cost": cost}


def of_workshop(state, entries):
    """Les frictions d'un Workshop fini, et sa durée."""
    frictions = workshop_frictions(state, entries)
    cost = _cost_of(state, entries, command="ballet:workshop", item=state.get("item", ""))
    return {"seconds": _seconds(entries), "frictions": frictions, "cost": cost}


def rehearsal_frictions(state, entries):
    """La liste des frictions d'une Rehearsal, finie ou non, sans son coût : la Scène la lit en cours de route."""
    frictions = _escalations(entries)
    frictions += _counted("rejections", state.get("round_trips", 0), "Critic rejection")
    frictions += _counted("red_proofs", state.get("red_proofs", 0), "red proof")
    frictions += _counted("red_mutations", state.get("red_mutations", 0), "red mutation")
    frictions += _counted("refused_reports", state.get("refused_reports", 0), "Dancer report refused", plural="Dancer reports refused")
    frictions += _nudges(entries)
    frictions += _idle(entries)
    frictions += _policy(state.get("violations", {}))
    frictions += _oversized(state.get("size", {}))
    return frictions


def workshop_frictions(state, entries):
    """La liste des frictions d'un Workshop, fini ou non, sans son coût."""
    frictions = _escalations(entries)
    frictions += _counted("refused_reports", state.get("refused_reports", 0), "Dramaturg report refused", plural="Dramaturg reports refused")
    frictions += _nudges(entries)
    frictions += _idle(entries)
    frictions += _policy({"dramaturg": state.get("violations", 0)})
    return frictions


def line(name, record):
    """Une ligne pour le `done` : `frictions of FEAT-007 (42 min): escalated: …; 1 red proof | cost ~$8.65 …`, ou `…: none`."""
    listed = "; ".join(friction["text"] for friction in record.get("frictions", [])) or "none"
    cost = f" | {ballet_cost.line_of(record['cost'])}" if record.get("cost") else ""
    return f"frictions of {name} ({_duration(record.get('seconds', 0))}): {listed}{cost}"


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


def _idle(entries):
    """Les avis `idle` du Monitor : le Conductor est resté sans nouvelles (marques `idle` du journal)."""
    count = sum(1 for entry in entries if entry.get("event") == "idle")
    if not count:
        return []
    return [{"kind": "idle", "count": count, "text": f"silent {count} time{'s' if count > 1 else ''}: Monitor idle notice{'s' if count > 1 else ''}"}]


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


def _cost_of(state, entries, command, item):
    """Le coût des sessions du worktree et du Conductor ; jamais une erreur : un journal illisible le rend absent."""
    window = _window(entries)
    if not state.get("worktree"):
        return {"missing": "no worktree in its state"}
    try:
        return ballet_cost.of_work(state["worktree"], state.get("repo", ""), command, item, window)
    except Exception as error:   # le coût est un confort : il ne doit jamais empêcher la fin
        return {"missing": f"journals unreadable: {type(error).__name__}"}


def _window(entries):
    """Du premier `begin` à la dernière entrée du journal : (début, fin), ou `None` sans entrée datée."""
    stamps = [datetime.fromisoformat(entry["at"]) for entry in entries if entry.get("at")]
    begins = [datetime.fromisoformat(entry["at"]) for entry in entries if entry.get("event") == "begin" and entry.get("at")]
    if not stamps:
        return None
    return (min(begins) if begins else min(stamps)), max(stamps)


def _seconds(entries):
    window = _window(entries)
    return max(0, round((window[1] - window[0]).total_seconds())) if window else 0


def _duration(seconds):
    minutes = round(seconds / 60)
    return f"{minutes} min" if minutes < 120 else f"{minutes // 60} h {minutes % 60:02d}"


def _shortened(text):
    text = " ".join(text.split())
    return text if len(text) <= ESCALATION_TEXT_LIMIT else text[:ESCALATION_TEXT_LIMIT - 1] + "…"
