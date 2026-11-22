"""Le Monitor de Ballet (OPP-01, OPP-02 étape 4) : un script sans LLM qui observe et signale à Maestro.

    python3 ballet_monitor.py once                   # un seul tour (à la main, pour essayer)
    python3 ballet_monitor.py run [--interval <s>]   # en boucle, 180 s par défaut : dans son propre terminal Orca

Il ne lance jamais rien et ne parle jamais au Director : il écrit dans la boîte de Maestro, depuis son terminal Orca
(`ORCA_TERMINAL_HANDLE`, comme les Conductors), et Maestro décide.

**Règle : le Monitor ne poste que des événements, c'est-à-dire des faits** (quoi, quand, des chiffres, des liens), jamais une
instruction ni une décision (« relance-le », « ferme-le », « redémarre »). Les décisions appartiennent à Maestro : les lignes
`DECISION:` que son script écrit sous le message (`ballet_maestro.py`), puis son skill. Un message du Monitor se lit sans
savoir ce que Maestro en fera. Quatre choses seulement :

- **Un élément qui devient lançable.** Pour chaque projet de `maestro.toml`, la file GitHub est lue par `ballet_program.py` (les
  `Feature`, `Bug` et `Task` au champ `Ballet status` `ready`, avec leurs bloqueurs ouverts : les liens « Blocked by » de
  GitHub). Un élément prêt mais qui attend un bloqueur ouvert est muet : il ne réveille pas Maestro. Chaque élément qui
  devient lançable (prêt et sans bloqueur ouvert, ou prêt avec une dépendance douteuse que seul le Director tranche) devient
  un `status`, sujet `<projet>#<N> · ready`, corps `#<N> · <type> · <priorité> · <titre> · <lien>` ; quand son dernier
  bloqueur vient de se fermer, une ligne `unblocked: #M closed` suit, et `dependency: <doute>` quand elle est douteuse. Au
  premier tour d'un projet, les éléments déjà lançables sont groupés en un seul message (sujet
  `<projet> · ready (<n> already)`, une ligne par élément). Les éléments prêts de chaque projet, bloqués compris, sont
  gardés avec leurs bloqueurs dans la base (`ballet_db.py`, table `ready`) : un élément encore lançable au tour suivant n'est pas signalé deux fois ; un élément qui quitte `ready` (ou
  se rebloque) puis redevient lançable l'est de nouveau. C'est aussi ce que lit `ballet_maestro.py ready`.
- **Un Conductor disparu.** Une ligne `running` du registre dont le terminal n'existe plus dans Orca devient un `status`
  `<projet>#<élément> · gone`, priorité `high`, et la ligne passe à `gone`, une seule fois. Un Conductor figé (terminal
  vivant, rien d'envoyé) n'est pas vu ici : c'est une autre opportunité.
- **Un Conductor fini resté ouvert.** Une ligne `finished` du registre, d'un Conductor que Maestro a lancé, dont le
  terminal vit encore au-delà de `[conductors] close_finished_after_minutes` (10 par défaut, 0 : jamais) devient un
  `status` `<projet>#<élément> · finished`, une seule fois (`finished_told` dans le registre). Le Monitor ne ferme rien :
  Maestro le fait (`ballet_launch.py close`), sur la décision du script (`DECISION: close`).
- **Le contexte de Maestro au-dessus du seuil.** Le bail de Maestro (`ballet_runtime.py`) note l'id de la session Claude de Maestro ; le
  Monitor lit son transcript (`ballet_context.py`) et, quand le contexte atteint `[maestro] restart_at_context_percent` de
  `[maestro] context_window_tokens` (30 % d'un million par défaut, 0 : jamais), écrit `maestro · context over threshold`
  (pourcentage, tokens, fenêtre, seuil, session), une seule fois par session (`context_told_session` dans `ballet_runtime.py`) :
  une session qui prend la suite (redémarrage, `/clear`) a un autre id, donc sa propre alerte. Un retour au-dessous du
  seuil (compaction) ne la réarme pas. Sans bail, il ne lit rien ; un bail sans id de session, un transcript introuvable
  ou un contexte plus grand que la fenêtre sont des erreurs du tour. Maestro décide (`DECISION: restart`).

Un envoi qui échoue n'est pas noté comme fait : le tour suivant le refait. `gh` ou Orca injoignable est une ligne d'erreur
du tour, jamais une panne de `run`.
"""

import json
import re
import sys
import time
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import ballet_conductors
import ballet_context
import ballet_db
import ballet_journal
import ballet_legacy
import ballet_maestro
import ballet_program
import ballet_runtime
from ballet_maestro import MaestroError

DEFAULT_INTERVAL = 180
KEPT = ("item", "number", "type", "title", "priority", "url", "blocked_by", "doubt")   # ce que le Monitor retient d'un élément prêt
READY_LINE = re.compile(r"^#(?P<number>\d+) · (?P<type>\w+) · ")
READY_SUBJECT = re.compile(r"^([^\s#]+)(?:#\S+)? · ready\b")
CONTEXT_SUBJECT = ballet_maestro.CONTEXT_SUBJECT
USAGE = "usage: once | run [--interval <seconds>]"


class UsageError(Exception):
    pass


@dataclass
class Report:
    """Ce qu'un tour a dit à Maestro, et ce qui l'a gêné."""
    told: list = field(default_factory=list)
    errors: list = field(default_factory=list)


# --- les tours ----------------------------------------------------------------


def once(orca, queue=ballet_program.ready_items, state=None):
    """Un tour : la file de chaque projet, puis les Conductors dont le terminal a disparu."""
    report = Report()
    _attempt(report, "state", lambda: ballet_legacy.refuse_if_pending(state))
    if report.errors:
        return report
    for alias, home in _projects(state):
        _attempt(report, alias, lambda: _watch_ready(alias, home, orca, queue, state, report))
    _attempt(report, "Conductors", lambda: _watch_gone(orca, state, report))
    _attempt(report, "finished Conductors", lambda: _watch_finished(orca, state, report))
    _attempt(report, "Maestro context", lambda: _watch_context(orca, state, report))
    return report


def run(interval, orca, queue=ballet_program.ready_items, state=None, tours=None, sleep=time.sleep):
    """Des tours à la suite, `interval` secondes entre deux ; `tours` les borne (les tests). Une erreur ne l'arrête pas."""
    done = 0
    while tours is None or done < tours:
        if done:
            sleep(interval)
        done += 1
        try:
            report = once(orca, queue, state)
        except Exception as error:  # le Monitor doit survivre à ce qu'il n'a pas prévu : le tour suivant réessaie
            report = Report(errors=[f"turn failed: {error}"])
        _show(report)


def _attempt(report, label, step):
    """Une panne d'un projet ou d'Orca est une ligne d'erreur ; les autres étapes du tour continuent."""
    try:
        step()
    except (ballet_program.ProgramError, MaestroError, *ballet_db.ERRORS, OSError, json.JSONDecodeError,
            tomllib.TOMLDecodeError) as error:
        report.errors.append(f"{label}: {error}")


def _projects(state):
    projects = ballet_maestro.read_config(state)["projects"]
    return [(alias, Path(project["path"])) for alias, project in sorted(projects.items())]


# --- un élément passé ready ----------------------------------------------------


def _watch_ready(alias, home, orca, queue, state, report):
    """Signale ce qui est devenu lançable, puis retient la file telle qu'elle est : ce qui en est sorti, ou s'est rebloqué,
    pourra revenir. Un élément prêt mais bloqué est retenu sans rien dire."""
    items = [_kept(item) for item in queue(home)]
    known = read_ready(state).get(alias)
    if known is None:
        _tell_first_turn(alias, _launchable(items), orca, state, report)
    else:
        for item in _newly_launchable(items, known):
            _tell_ready(alias, item, _line_before(item, known), orca, state, report)
            known = [*[other for other in known if other["item"] != item["item"]], item]
            _save_ready(alias, known, state)
    _save_ready(alias, items, state)


def _tell_first_turn(alias, items, orca, state, report):
    """Au premier tour d'un projet : un seul message pour tous les éléments déjà lançables, pour ne pas inonder la boîte."""
    if not items:
        return
    subject = f"{alias} · ready ({len(items)} already)"
    _send(subject, "\n".join(_ready_line(item) for item in items), "normal", orca, state, report)


def _tell_ready(alias, item, before, orca, state, report):
    _send(f"{alias}#{item['number']} · ready", _ready_body(item, before), "normal", orca, state, report)


def _launchable(items):
    """Ce qui mérite un réveil : tout sauf ce qui attend un bloqueur ouvert."""
    return [item for item in items if not ballet_program.waits(item)]


def _newly_launchable(items, known):
    already = {item["item"] for item in _launchable(known)}
    return [item for item in _launchable(items) if item["item"] not in already]


def _line_before(item, known):
    """L'élément tel que le tour précédent le connaissait ; rien s'il n'était pas prêt."""
    return next((other for other in known if other["item"] == item["item"]), None)


def _ready_body(item, before):
    """La ligne de l'élément, puis ce qui a changé pour ses dépendances : un doute, ou les bloqueurs qui viennent de se fermer."""
    if item.get("doubt"):
        return f"{_ready_line(item)}\ndependency: {item['doubt']}"
    freed = [blocker["item"] for blocker in (before or {}).get("blocked_by", []) if blocker not in item.get("blocked_by", [])]
    return f"{_ready_line(item)}\nunblocked: {', '.join(freed)} closed" if freed else _ready_line(item)


def _ready_line(item):
    return f"#{item['number']} · {item['type']} · {item['priority'] or 'no priority'} · {item['title']} · {item['url']}"


def _kept(item):
    return {name: item[name] for name in KEPT}


def project_of_ready_subject(subject):
    """L'alias du projet d'un sujet `<projet>#<N> · ready` ou `<projet> · ready (…)` ; vide pour tout autre sujet."""
    found = READY_SUBJECT.match(subject)
    return found.group(1) if found else ""


# --- un Conductor disparu ------------------------------------------------------


def _watch_gone(orca, state, report):
    """Chaque Conductor `running` dont le terminal n'est plus dans Orca : signalé puis marqué `gone`, une fois."""
    running = {key: line for key, line in ballet_conductors.read(state).items()
               if ballet_conductors.state_of(line) == ballet_conductors.RUNNING}
    if not running:
        return
    alive = ballet_maestro.live_terminals(orca)
    for key, line in sorted(running.items()):
        if line["terminal"] not in alive:
            _attempt(report, key, lambda: _tell_gone(key, line, orca, state, report))


def _tell_gone(key, line, orca, state, report):
    body = (f"The Conductor of {key} is gone: its terminal {line['terminal']} no longer exists in Orca "
            f"({line.get('kind') or 'kind unknown'}, started {line.get('started') or 'at an unknown time'}, "
            f"last event {line.get('event') or 'none'}).")
    _send(f"{key} · gone", body, "high", orca, state, report)
    ballet_conductors.mark_gone(key, line["terminal"], state)


# --- un Conductor fini resté ouvert ----------------------------------------------


def _watch_finished(orca, state, report):
    """Chaque Conductor lancé par Maestro, fini depuis plus que le délai, dont le terminal vit encore : signalé, une fois."""
    delay = ballet_maestro.close_delay_minutes(ballet_maestro.read_config(state))
    registry = ballet_conductors.read(state)
    if not delay or not any(ballet_conductors.state_of(line) == ballet_conductors.FINISHED for line in registry.values()):
        return
    alive = ballet_maestro.live_terminals(orca)
    for key, line in sorted(ballet_conductors.finished_open(registry, delay, alive).items()):
        _attempt(report, key, lambda: _tell_finished(key, line, delay, orca, state, report))


def _tell_finished(key, line, delay, orca, state, report):
    url = f" Remote Control {line['url']}." if line.get("url") else ""
    body = (f"The {line.get('kind')} Conductor of {key} finished at {line.get('seen')} and its terminal {line['terminal']} "
            f"is still open after {delay} min.{url}")
    _send(f"{key} · finished", body, "normal", orca, state, report)
    ballet_conductors.note_finished_told(key, line["terminal"], state)


# --- le contexte de Maestro ------------------------------------------------------


def _watch_context(orca, state, report):
    """Le contexte de la session Maestro du bail, signalé une fois par session quand il atteint le seuil. Sans bail, ou
    avec un seuil de 0, rien n'est lu."""
    config = ballet_maestro.read_config(state)
    threshold = ballet_maestro.restart_percent(config)
    runtime = ballet_runtime.read(state)
    if not threshold or not runtime["lease_owner"]:
        return
    session = _need(runtime["lease_session"])
    if read_context_told(state) == session:
        return
    used = _context_used(session)
    if used is None:
        return
    window = ballet_maestro.context_window(config)
    if used > window:
        raise MaestroError(f"Maestro's context ({used} tokens) is above context_window_tokens ({window}) in {ballet_maestro.CONFIG_NAME}: "
                           "the window is wrong")
    if used * 100 >= threshold * window:
        _tell_context(used, window, threshold, session, orca, state, report)


def _need(session):
    """L'id de session du bail ; un bail qui n'en a pas est une panne à dire."""
    if not session:
        raise MaestroError(f"Maestro's lease has no Claude session id: Maestro's context is not watched "
                           f"(claim runs inside Claude, where {ballet_maestro.SESSION_VARIABLE} is set)")
    return session


def _context_used(session):
    """Le contexte courant de la session ; `None` tant que son transcript n'a pas de message de l'assistant."""
    transcript = ballet_context.transcript_of(session)
    if not transcript:
        raise MaestroError(f"no transcript for session {session} under {ballet_context.claude_home() / 'projects'}")
    return ballet_context.used_tokens(transcript)


def _tell_context(used, window, threshold, session, orca, state, report):
    body = f"Maestro's context is {used} tokens · {used * 100 // window}% of {window} · threshold {threshold}% · session {session}"
    _send(CONTEXT_SUBJECT, body, "normal", orca, state, report)
    _save_context_told(session, state)


# --- la boîte ------------------------------------------------------------------


def _send(subject, body, priority, orca, state, report):
    ballet_maestro.post_status(ballet_maestro.mailbox_run(state), subject, body, priority, orca)
    report.told.append(subject)


# --- la file vue, le contexte signalé ----------------------------------------------


def read_ready(state=None):
    """Les éléments prêts de chaque projet, tels que le dernier tour les a vus : alias → éléments, dans l'ordre de la
    file. Un projet pas encore vu n'y figure pas."""
    with ballet_db.reading(state) as connection:
        return {row["project"]: json.loads(row["items"]) for row in connection.execute("SELECT project, items FROM ready")}


def read_context_told(state=None):
    """L'id de la session Maestro dont le dépassement du seuil a été signalé ; vide si aucune."""
    return ballet_runtime.read(state)["context_told_session"]


def _save_ready(alias, items, state):
    with ballet_db.writing(state) as connection:
        connection.execute("INSERT OR REPLACE INTO ready (project, items, seen_at) VALUES (?, ?, ?)",
                           (alias, json.dumps(items, ensure_ascii=False), ballet_journal.now_iso()))


def _save_context_told(session, state):
    ballet_runtime.update(state, context_told_session=session)


# --- ligne de commande ---------------------------------------------------------


def _show(report):
    """Une ligne par message envoyé ou erreur, datée ; rien quand le tour n'a rien à dire."""
    stamp = datetime.now().strftime("%H:%M:%S")
    for subject in report.told:
        print(f"{stamp} told Maestro: {subject}", flush=True)
    for error in report.errors:
        print(f"{stamp} problem: {error}", file=sys.stderr, flush=True)


def main(argv, orca=None, queue=ballet_program.ready_items):
    """Un tour (`once`, 1 s'il a eu un problème) ou des tours sans fin (`run`) ; 2 sur un usage invalide."""
    orca = orca or ballet_maestro.run_orca
    try:
        arguments = argv[1:]
        if arguments == ["once"]:
            report = once(orca, queue)
            _show(report)
            if not report.told and not report.errors:
                print("nothing new")
            return 1 if report.errors else 0
        if arguments[:1] == ["run"]:
            run(_interval(arguments[1:]), orca, queue)
            return 0
        raise UsageError(USAGE)
    except UsageError as error:
        print(error, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


def _interval(arguments):
    if not arguments:
        return DEFAULT_INTERVAL
    if len(arguments) == 2 and arguments[0] == "--interval":
        try:
            seconds = float(arguments[1])
        except ValueError:
            seconds = 0
        if seconds > 0:
            return seconds
    raise UsageError(USAGE)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
