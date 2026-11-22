"""L'état de Maestro, le point d'entrée du Director (OPP-02) : sa boîte Orca, ses projets, son bail, et les commandes de sa session.

    python3 ballet_maestro.py mailbox                        # crée la boîte de Maestro, une seule fois
    python3 ballet_maestro.py monitor                        # crée le terminal du Monitor (`ballet_monitor.py run`), une seule fois
    python3 ballet_maestro.py maestro                        # lance la session Maestro elle-même dans son terminal Orca, une seule fois
    python3 ballet_maestro.py project add <alias> <chemin>   # enregistre un projet (ou change son chemin)
    python3 ballet_maestro.py project list                   # les projets connus
    python3 ballet_maestro.py claim [--take-over]            # prend le bail : une seule session Maestro lit la boîte
    python3 ballet_maestro.py wait --owner <jeton>           # attend la boîte (en arrière-plan), affiche ce qui arrive
    python3 ballet_maestro.py recap --owner <jeton>          # au démarrage : le non-lu (consommé) et l'historique
    python3 ballet_maestro.py status                         # les sessions ouvertes de chaque projet, les Conductors lancés, les éléments prêts
    python3 ballet_maestro.py ready                          # les éléments prêts sans Conductor, dans l'ordre de la file, avec la décision
    python3 ballet_maestro.py pause | resume                 # plus rien ne part seul (`~/.ballet/auto_launch_paused`) | tout repart
    python3 ballet_maestro.py tell <projet>#<élément> <texte>   # la réponse du Director, au terminal du Conductor

L'état vit dans `~/.ballet/maestro.toml` (`BALLET_HOME` pour un autre dossier) :

    [mailbox]                 la boîte : un terminal Orca vide, à elle seule, et la Run créée `--from` lui
    terminal = "term_…"
    run = "run_…"
    previous_run = "run_…"    la Run d'une boîte recréée, que `recap` relit une dernière fois puis oublie

    [lease]                   le bail de lecture : lire la boîte consomme les messages, une seule session le fait
    owner = "…"               le jeton de la session Maestro (`claim`) ; vide, personne
    pid = 0                   le processus de son attente en cours (`wait`), 0 sinon
    renewed = "…"             la date ISO de la dernière prise, ou de la fin de la dernière attente

    [monitor]                 le terminal Orca du Monitor (`monitor` le crée)
    terminal = "term_…"

    [maestro]                 le terminal Orca de la session Maestro (`maestro` le crée)
    terminal = "term_…"

    [projects.antimurphy]     un projet par alias
    path = "/chemin/vers/antimurphy"
    auto_launch = ["Task", "Bug"]    les types que Maestro lance seul ; vide ou absent : il demande toujours

    [limits]                  les plafonds de `ballet_launch.py` (facultatif ; ces valeurs par défaut)
    max_running = 3           Conductors vivants en même temps, tous projets confondus
    max_per_day = 10          lancements par jour (jour local)

    [conductors]              (facultatif ; cette valeur par défaut)
    close_finished_after_minutes = 10   un Conductor fini dont le terminal reste ouvert au-delà : le Monitor le signale
                                        (`<projet>#<élément> · finished`) et Maestro le ferme ; 0 : jamais

La règle de lancement automatique se décide ici, dans `decide` : un élément passé `ready` (signalé par le Monitor) est
lancé seul quand son type est dans `auto_launch` de son projet et que le drapeau `~/.ballet/auto_launch_paused` n'existe
pas (`pause` le pose, `resume` le retire) ; sinon Maestro demande au Director. `wait` et `recap` écrivent le verdict sous
chaque élément `· ready` : `DECISION: launch` ou `DECISION: ask the Director (<raison>)`. Un lancement refusé par un
plafond laisse l'élément dans `ready` : `ready` le liste tant qu'il n'a pas de Conductor et que le Monitor le voit prêt.

Les dépendances (les liens « Blocked by » de GitHub, lus par `ballet_program.py` et gardés par le Monitor) passent avant la
règle `auto_launch` : un élément prêt dont un bloqueur est ouvert est `DECISION: wait (blocked by #M, open)` ; une dépendance
douteuse (bloqueur fermé *not planned*, cycle, bloqueur illisible) est `DECISION: ask the Director (<raison>)`, même pour un
type confié à l'auto. `ready` et `status` montrent aussi ces éléments bloqués.

Sous chaque `status` `<projet>#<élément> · finished` du Monitor, `wait` et `recap` écrivent `DECISION: close` (Maestro
ferme le terminal par `ballet_launch.py close`, puis le dit) ou `DECISION: ask the Director (<raison>)` quand la ligne du
registre a changé depuis (relancé, autre terminal, déjà fermé).

`maestro` lance la session Maestro elle-même, comme `monitor` lance le Monitor : un terminal Orca `maestro` où tourne
`claude --remote-control 'ballet maestro' '/ballet:maestro'` (le prompt avant les options ; `BALLET_MAESTRO_COMMAND` remplace
`claude`, pour essayer sans tokens ; `BALLET_HOME` est transmis s'il est posé). Il ne fait rien quand le terminal noté vit
encore, ni quand une session Maestro tient un bail vivant (deux sessions se disputeraient la boîte : il le dit et ne crée
rien). La session créée prend elle-même le bail (`claim`) ; la rouvrir ailleurs se heurte à ce bail, et `--take-over` ne
se fait que sur le oui du Director.

Il n'existe jamais deux boîtes : `mailbox` ne fait rien quand le terminal noté vit encore dans Orca, et un verrou
(`maestro.lock`) empêche deux appels de créer chacun la sienne. Chaque écriture passe par un fichier temporaire, puis
un renommage.

Le bail est vivant tant que le `pid` de l'attente tourne, ou que `renewed` a moins de 10 minutes : c'est le temps qu'a la
session, entre deux attentes, pour traiter un message. `claim` refuse un bail vivant ; `claim --take-over` arrête l'attente
de l'ancien propriétaire et le remplace (après un `/clear`, ou une session morte). `wait` ne lit la boîte que pour le jeton
qui tient le bail ; sinon la session n'est plus Maestro.

`wait` et `recap` notent, pour chaque `status` de sujet `<projet>#<élément> · <événement>`, le terminal expéditeur et
l'événement dans le registre des Conductors (`ballet_conductors.py`, `~/.ballet/conductors.json`, que `ballet_launch.py`
remplit déjà au lancement) : c'est où `tell` écrit ; un `done` clôt la ligne. Ils lisent en consommant (jamais `--peek`) :
un message lu n'est plus non lu.

Les Conductors (`ballet_rehearsal.py`, `ballet_workshop.py`) appellent `announce` quand ils écrivent `NEXT: escalate`
ou `NEXT: done` : un message `status`, priorité `high`, sujet `<projet>#<élément> · <événement>`, dans la boîte. Sans
`maestro.toml` ou sans boîte, rien n'est envoyé ; un envoi qui échoue n'arrête jamais le Conductor.
"""

import json
import os
import re
import secrets
import shlex
import signal
import subprocess
import sys
import tomllib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ballet_conductors
import ballet_program
import ballet_state

CONFIG_NAME = "maestro.toml"
LOCK_NAME = "maestro.lock"
MAILBOX_TITLE = "maestro-mailbox"
MAILBOX_OBJECTIVE = "Maestro's mailbox: the Conductors and the Monitor write here, Maestro reads"
ANNOUNCED = ("escalate", "done")
DEFAULT_CLOSE_MINUTES = 10
FINISHED_SUBJECT = re.compile(r"^(\S+#\S+) · finished$")   # le Monitor : un Conductor fini, terminal encore ouvert
TERMINAL_IN_BODY = re.compile(r"\bterminal (term_\S+?)[,.\s]")
ALIAS = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
HEADER = "# Maestro (OPP-02), written by ballet_maestro.py: edit it while no Maestro command runs.\n"
LEASE_TTL = timedelta(minutes=10)   # le temps de la session, entre deux attentes, pour traiter un message
WAIT_TIMEOUT_MS = 600_000           # une attente qui expire sans message est relancée : `wait` ne rend la main qu'avec du courrier
RECAP_LIMIT = 10                    # les derniers messages de l'historique relus au démarrage
EMPTY_LEASE = {"owner": "", "pid": 0, "renewed": ""}
TARGET = re.compile(r"^[^\s#]+#\S+$")
PAUSE_FLAG = "auto_launch_paused"
MONITOR_TITLE = "ballet-monitor"
MONITOR_SCRIPT = Path(__file__).resolve().with_name("ballet_monitor.py")
MAESTRO_TITLE = "maestro"
MAESTRO_NAME = "ballet maestro"          # le nom Remote Control de la session, celui qu'on cherche dans l'app Claude
MAESTRO_PROMPT = "/ballet:maestro"
MAESTRO_COMMAND_VARIABLE = "BALLET_MAESTRO_COMMAND"
DEFAULT_AGENT = "claude"
USAGE = ("usage: mailbox | monitor | maestro | project add <alias> <path> | project list | claim [--take-over] | wait --owner <token> "
         "| recap --owner <token> | status | ready | pause | resume | tell <project>#<item> <text>")


class MaestroError(Exception):
    """Maestro ne peut pas faire ce qu'on lui demande : le message dit pourquoi."""


class UsageError(Exception):
    pass


# --- les commandes ------------------------------------------------------------


def mailbox(orca, state=None):
    """La boîte de Maestro, créée une seule fois : un terminal Orca vide, puis une Run créée `--from` lui. Si le
    terminal noté vit encore, rien ne change ; sinon une nouvelle boîte le remplace, et l'ancienne Run est gardée
    pour une dernière lecture."""
    with ballet_state.locked(state):
        config = read_config(state)
        box = config["mailbox"]
        alive = bool(box.get("terminal")) and _terminal_alive(box["terminal"], orca)
        if alive and box.get("run"):
            return f"mailbox already there: terminal {box['terminal']}, run:{box['run']}"
        box = box if alive else _replace_terminal(config, orca, state)
        box["run"] = _new_run(box["terminal"], orca)
        write_config(config, state)
        return f"mailbox created: terminal {box['terminal']}, run:{box['run']}"


def monitor(orca, state=None):
    """Le terminal du Monitor, créé une seule fois : il lance `ballet_monitor.py run`. Si le terminal noté vit encore,
    rien ne change ; sinon un nouveau le remplace. Une Orca injoignable lève : on ne crée jamais un second Monitor à
    l'aveugle."""
    with ballet_state.locked(state):
        config = read_config(state)
        handle = config.get("monitor", {}).get("terminal", "")
        if handle and _terminal_alive(handle, orca):
            return f"monitor already there: terminal {handle}"
        receipt = json.loads(orca(["terminal", "create", "--title", MONITOR_TITLE, "--command", _monitor_command(), "--json"]))
        handle = first_id(receipt, "term_", "orca terminal create")
        config["monitor"] = {"terminal": handle}
        write_config(config, state)
        return f"monitor created: terminal {handle}"


def _monitor_command():
    """`python3 <clone>/scripts/ballet_monitor.py run`, avec `BALLET_HOME` quand il est posé : le Monitor lit le même dossier d'état."""
    home = os.environ.get("BALLET_HOME")
    return " ".join([*([f"BALLET_HOME={shlex.quote(home)}"] if home else []), "python3", shlex.quote(str(MONITOR_SCRIPT)), "run"])


def maestro(orca, state=None):
    """La session Maestro, lancée une seule fois dans son terminal Orca. Si le terminal noté vit encore, ou si une session
    Maestro tient un bail vivant, rien n'est créé (deux sessions se disputeraient la boîte) ; sinon un nouveau terminal
    la lance et le remplace. Une Orca injoignable lève : on ne crée jamais une seconde session à l'aveugle."""
    with ballet_state.locked(state):
        config = read_config(state)
        handle = config.get("maestro", {}).get("terminal", "")
        if handle and _terminal_alive(handle, orca):
            return f"maestro already there: terminal {handle}"
        if _lease_alive(config["lease"]):
            return f"maestro not created: {_lease_held_message(config['lease'])}"
        receipt = json.loads(orca(["terminal", "create", "--title", MAESTRO_TITLE, "--command", _maestro_command(), "--json"]))
        handle = first_id(receipt, "term_", "orca terminal create")
        config["maestro"] = {"terminal": handle}
        write_config(config, state)
        return f"maestro created: terminal {handle}"


def _maestro_command():
    """`<agent> --remote-control 'ballet maestro' '/ballet:maestro'` : le prompt avant les options, comme pour un Conductor ;
    avec `BALLET_HOME` quand il est posé : la session lit le même dossier d'état."""
    agent = shlex.split(os.environ.get(MAESTRO_COMMAND_VARIABLE) or DEFAULT_AGENT)
    command = shlex.join([*agent, "--remote-control", MAESTRO_NAME, MAESTRO_PROMPT])
    home = os.environ.get("BALLET_HOME")
    return f"BALLET_HOME={shlex.quote(home)} {command}" if home else command


def add_project(alias, path, state=None):
    """Enregistre un projet sous son alias, par son chemin absolu ; un alias connu change de chemin."""
    if not ALIAS.match(alias):
        raise MaestroError(f"not an alias: {alias} (lowercase letters, digits, '-' or '_')")
    folder = Path(path).expanduser().resolve()
    if not folder.is_dir():
        raise MaestroError(f"no folder at {folder}")
    with ballet_state.locked(state):
        config = read_config(state)
        config["projects"].setdefault(alias, {})["path"] = str(folder)   # `auto_launch` d'un projet connu reste
        write_config(config, state)
    return f"project {alias}: {folder}"


def list_projects(state=None):
    projects = read_config(state)["projects"]
    if not projects:
        return "no project yet: python3 ballet_maestro.py project add <alias> <path>"
    return "\n".join(f"{alias}  {project['path']}" for alias, project in sorted(projects.items()))


def announce(step, home, orca, state=None):
    """Prévient Maestro qu'un Conductor escalade ou a fini : un `status` dans sa boîte. Sans boîte, rien n'est
    envoyé ; un échec devient une ligne du pas, jamais une panne."""
    if step.next not in ANNOUNCED or not step.item:
        return
    try:
        config = read_config(state)
    except (OSError, tomllib.TOMLDecodeError) as error:
        step.done.append(f"Maestro not told: {_config_path(state)} unreadable: {error}")
        return
    run = config["mailbox"].get("run")
    if not run:
        return
    subject = f"{project_of(home, config)}#{step.item.lstrip('#')} · {step.next}"
    try:
        post_status(run, subject, step.render(), "high", orca)
    except Exception as error:  # l'annonce n'est qu'un plus : rien ne doit arrêter le Conductor
        step.done.append(f"Maestro not told ({subject}): {error}")
        return
    step.done.append(f"Maestro told: {subject}")


def post_status(run, subject, body, priority, orca):
    """Un message `status` dans la boîte : le chemin d'envoi des Conductors et du Monitor, depuis le terminal Orca de
    l'expéditeur (`ORCA_TERMINAL_HANDLE`)."""
    orca(["orchestration", "send", "--to", f"run:{run}", "--type", "status", "--priority", priority,
          "--subject", subject, "--body", body])


def mailbox_run(state=None):
    """La Run de la boîte, où écrire ; une machine sans boîte est refusée."""
    run = read_config(state)["mailbox"].get("run")
    if not run:
        raise MaestroError("no mailbox yet: run ballet_maestro.py mailbox")
    return run


def project_of(home, config):
    """L'alias du projet dont `home` est le dossier, sinon le nom du dossier."""
    folder = Path(home).resolve()
    return next((alias for alias, project in config["projects"].items() if Path(project["path"]).resolve() == folder),
                folder.name)


def claim(take_over=False, state=None):
    """Le bail de lecture de la boîte, pour une seule session : refusé quand une autre le tient vivant, sauf `take_over`,
    qui arrête d'abord l'attente de l'ancien propriétaire. Rend le jeton de la nouvelle propriétaire."""
    with ballet_state.locked(state):
        config = read_config(state)
        lease = config["lease"]
        if _lease_alive(lease) and not take_over:
            raise MaestroError(_lease_held_message(lease))
        _stop_the_wait(lease["pid"])
        owner = secrets.token_hex(8)
        config["lease"] = {"owner": owner, "pid": 0, "renewed": _now()}
        write_config(config, state)
    return f"lease claimed, owner {owner}"


def wait(owner, orca, state=None):
    """Attend un message dans la boîte, puis le rend lisible. Seul le jeton qui tient le bail lit : lire consomme.
    L'attente se note dans le bail (son pid) le temps qu'elle dure, et note le terminal de chaque Conductor qui écrit."""
    box = _take_the_wait(owner, state)
    try:
        messages = _wait_for_messages(box, orca)
        ballet_conductors.note_events(messages, state)
    finally:
        _release_the_wait(owner, state)
    return _render_messages(messages, state)


def recap(owner, orca, state=None):
    """Ce qui s'est dit dans la boîte pendant l'absence de la session : le non-lu, consommé ici pour qu'aucun `wait`
    ne le redonne, et les derniers messages de l'historique (un message lu juste avant la mort d'une session n'est
    plus non lu), ceux de la boîte précédente compris, qu'on oublie ensuite. Seul le jeton qui tient le bail lit."""
    box = _owned_mailbox(owner, state)
    unread = _consume_unread(box, orca)
    ballet_conductors.note_events(unread, state)
    history = [message for run in _runs_of(box) for message in _history_of(run, orca)]
    _forget_previous_run(state)
    return _render_history(_latest(history), {message.get("id") for message in unread}, state)


def status(orca, state=None):
    """Les sessions ouvertes de chaque projet, une ligne chacune (élément, Rehearsal courante, état, terminal connu),
    puis les Conductors du registre, avec l'état de leur terminal, puis les éléments prêts qui attendent un Conductor."""
    config = read_config(state)
    registry = ballet_conductors.read(state)
    sessions = [_session_line(alias, session, registry) for alias, project in sorted(config["projects"].items())
                for session in sessions_of(Path(project["path"]))]
    launched = _conductor_lines(registry, orca)
    waiting = _ready_lines(config, registry, state)
    return ("\n".join(sessions or ["no open session in any project"])
            + (f"\n\nConductors ({_closing_rule(config)}):\n" + "\n".join(launched) if launched else "")
            + ("\n\nReady, no Conductor yet:\n" + "\n".join(waiting) if waiting else ""))


def ready(state=None):
    """Les éléments prêts sans Conductor, dans l'ordre de la file, chacun avec la décision de la règle de lancement :
    ceux que le Monitor voit encore `ready` et qu'aucun Conductor vivant ne joue. Un lancement refusé par un plafond y reste."""
    lines = _ready_lines(read_config(state), ballet_conductors.read(state), state)
    return "\n".join(lines) if lines else "no item is waiting: every ready item has its Conductor (or the Monitor has not seen any)"


def decision(project, kind, state=None, number=None):
    """`launch` quand le type est confié à l'auto par son projet, que rien n'est en pause et que le dernier Conductor de
    l'élément n'a pas disparu ; sinon `ask the Director (<raison>)`. C'est ici que cela se décide : l'agent ne fait que
    relayer le verdict."""
    return _decision(project, kind, read_config(state), state, number)


def pause(state=None):
    """Pose le drapeau : rien ne part plus seul, Maestro demande toujours, jusqu'à `resume`."""
    flag = _pause_flag(state)
    if flag.exists():
        return "auto launch was already paused"
    ballet_state.write_atomically(flag, _now() + "\n")
    return "auto launch paused: nothing is launched on its own, Maestro asks the Director every time (resume to lift it)"


def resume(state=None):
    """Retire le drapeau : la règle de chaque projet s'applique de nouveau."""
    flag = _pause_flag(state)
    if not flag.exists():
        return "auto launch was not paused"
    flag.unlink()
    return "auto launch resumed: the projects' auto_launch rule applies again"


def _decision(project, kind, config, state, number=None, seen=None):
    if project not in config["projects"]:
        return f"ask the Director (unknown project {project})"
    dependencies = _dependency_decision(project, number, state, seen)
    if dependencies:
        return dependencies
    if _pause_flag(state).exists():
        return "ask the Director (auto launch is paused)"
    trusted = config["projects"][project].get("auto_launch", [])
    if not _is_list_of_text(trusted):
        return f"ask the Director ([projects.{project}] auto_launch must be a list of types)"
    if kind.casefold() not in (entrusted.casefold() for entrusted in trusted):
        return f"ask the Director ({kind} is not in auto_launch of {project})"
    if number is not None and _conductor_gone(f"{project}#{number}", state):
        return "ask the Director (its last Conductor is gone: relaunching on its own could loop)"
    return "launch"


def _dependency_decision(project, number, state, seen=None):
    """`wait (blocked by #M, open)` ou `ask the Director (<doute>)` d'après ce que le Monitor a vu de l'élément (ou ce
    que `ready` vient de relire) ; vide sinon."""
    kept = seen if seen is not None else _kept_item(project, number, state)
    if ballet_program.waits(kept):
        return "wait (blocked by " + ", ".join(blocker["item"] for blocker in kept["blocked_by"]) + ", open)"
    if kept.get("doubt"):
        return f"ask the Director ({kept['doubt']})"
    return ""


def _kept_item(project, number, state):
    """L'élément tel que le dernier tour du Monitor l'a vu ; vide quand le Monitor ne l'a pas vu (ou sans numéro)."""
    if number is None:
        return {}
    import ballet_monitor
    return next((item for item in ballet_monitor.read_ready(state).get(project, []) if str(item["number"]) == str(number)), {})


def _conductor_gone(key, state):
    """Le dernier Conductor de l'élément a disparu sans finir : seul le Director décide de le relancer."""
    line = ballet_conductors.read(state).get(key)
    return bool(line) and ballet_conductors.state_of(line) == ballet_conductors.GONE


def _is_list_of_text(value):
    return isinstance(value, list) and all(isinstance(entry, str) for entry in value)


def _pause_flag(state=None):
    return ballet_state.state_dir(state) / PAUSE_FLAG


def _ready_lines(config, registry, state):
    """Un élément prêt par ligne : `<projet>#<N>  <type>  <priorité>  <titre>  <lien>  DECISION: …`, projets par alias,
    chacun dans l'ordre de sa file. Un élément joué par un Conductor vivant n'y est plus."""
    import ballet_monitor
    lines = []
    for alias, items in sorted(ballet_monitor.read_ready(state).items()):
        if alias in config["projects"]:
            items = _with_live_blockers(items, config["projects"][alias])
        for item in items:
            if alias in config["projects"] and not _is_running(registry.get(f"{alias}#{item['number']}")):
                verdict = _decision(alias, item["type"], config, state, item["number"], seen=item)
                lines.append(f"{alias}#{item['number']}  {item['type']}  {item['priority'] or '-'}  {item['title']}  {item['url']}  "
                             f"DECISION: {verdict}")
    return lines


def _with_live_blockers(items, project):
    """Les bloqueurs relus sur GitHub quand un élément attend : le dernier tour du Monitor peut dater de quelques
    minutes, et un `done` vient peut-être de fermer le bloqueur. Une lecture par projet, seulement s'il a un élément
    bloqué ; GitHub injoignable, la vue du Monitor reste."""
    if not any(ballet_program.waits(item) for item in items):
        return items
    live = _live_ready(project["path"])
    if live is None:
        return items
    found = {str(item["number"]): item for item in live}
    return [{**item, **_dependencies_of(found.get(str(item["number"])))} if ballet_program.waits(item) else item for item in items]


def _dependencies_of(live_item):
    if not live_item:
        return {}
    return {key: live_item[key] for key in ("blocked_by", "launchable", "doubt") if key in live_item}


def _live_ready(project_dir):
    try:
        return ballet_program.ready_items(project_dir)
    except ballet_program.ProgramError:
        return None


def _is_running(line):
    return bool(line) and ballet_conductors.state_of(line) == ballet_conductors.RUNNING


def tell(target, text, orca, state=None):
    """La réponse du Director, tapée dans le terminal du Conductor de `<projet>#<élément>` : le Conductor l'écrit en
    message Ballet et la reçoit lui-même. Un élément inconnu, ou un terminal disparu, est refusé."""
    handle = _known_terminal(target, ballet_conductors.read(state))
    if not _terminal_alive(handle, orca):
        raise MaestroError(f"the terminal {handle} of {target} is gone: the Conductor is not running anymore")
    orca(["terminal", "send", "--terminal", handle, "--text", f"Director answers: {text}", "--enter"])
    return f"told {target} (terminal {handle})"


def _known_terminal(target, registry):
    if not TARGET.match(target):
        raise MaestroError(f"not an item: {target} (expected <project>#<item>, e.g. antimurphy#12)")
    if target not in registry:
        known = ", ".join(sorted(registry)) or "none yet"
        raise MaestroError(f"no terminal known for {target}: a Conductor is known once Maestro launches it, or it escalates or finishes (known: {known})")
    return registry[target]["terminal"]


# --- le bail ---------------------------------------------------------------


def _lease_alive(lease):
    """Vivant : un propriétaire dont l'attente tourne, ou qui a renouvelé le bail il y a moins de dix minutes."""
    return bool(lease["owner"]) and (_wait_runs(lease["pid"]) or _renewed_recently(lease["renewed"]))


def _renewed_recently(renewed):
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(renewed) < LEASE_TTL
    except ValueError:   # pas de date, ou illisible : le bail n'a pas été renouvelé
        return False


def _lease_held_message(lease):
    where = f"its wait is running (pid {lease['pid']})" if _wait_runs(lease["pid"]) else f"renewed {lease['renewed']}"
    return (f"another Maestro session holds the lease ({where}). Two sessions reading the mailbox would steal each "
            "other's messages. If that session is gone, or you cleared it, take over: claim --take-over")


def _stop_the_wait(pid):
    if _wait_runs(pid):
        os.kill(pid, signal.SIGTERM)


def _wait_runs(pid):
    """Le processus est-il encore une attente de Maestro ? Un pid qu'un autre programme a repris ne compte pas."""
    if not pid or pid <= 0:
        return False
    shown = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
    return "ballet_maestro.py" in shown and " wait" in shown


def _take_the_wait(owner, state):
    """Le jeton tient le bail et aucune autre attente ne tourne pour lui : l'attente note son pid. Rend la boîte."""
    with ballet_state.locked(state):
        config = read_config(state)
        lease = config["lease"]
        if lease["owner"] != owner:
            raise MaestroError("this session is not Maestro anymore: " + _who_holds(lease))
        if _wait_runs(lease["pid"]) and lease["pid"] != os.getpid():
            raise MaestroError(f"a wait of this session is already running (pid {lease['pid']}): one at a time")
        box = _checked_mailbox(config)
        config["lease"] = {**lease, "pid": os.getpid(), "renewed": _now()}
        write_config(config, state)
    return box


def _release_the_wait(owner, state):
    """L'attente finie : pid remis à 0 et bail renouvelé, sauf si un autre a pris le bail entre-temps."""
    with ballet_state.locked(state):
        config = read_config(state)
        if config["lease"]["owner"] != owner:
            return
        config["lease"] = {**config["lease"], "pid": 0, "renewed": _now()}
        write_config(config, state)


def _who_holds(lease):
    if not lease["owner"]:
        return "no lease is held, run claim"
    return "another session holds the lease, ask the Director whether to claim --take-over"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _stopped_by_take_over():
    """Un `SIGTERM` (un autre Maestro prend le bail) arrête l'attente, et Orca avec elle : la session en est prévenue."""
    def stop(signum, frame):
        raise MaestroError("this session is not Maestro anymore: its wait was stopped (another session took over)")
    previous = signal.signal(signal.SIGTERM, stop)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


# --- la boîte, lue ------------------------------------------------------------


def _checked_mailbox(config):
    box = config["mailbox"]
    if not box.get("terminal") or not box.get("run"):
        raise MaestroError("no mailbox yet: run ballet_maestro.py mailbox")
    return box


def _wait_for_messages(box, orca):
    """Une lecture qui consomme (jamais `--peek`), bloquée jusqu'au premier message ; une attente qui expire repart."""
    while True:
        answer = json.loads(orca(["orchestration", "check", "--terminal", box["terminal"], "--run", box["run"],
                                  "--wait", "--timeout-ms", str(WAIT_TIMEOUT_MS), "--json"]))
        if answer["result"]["messages"]:
            return answer["result"]["messages"]


def _owned_mailbox(owner, state):
    """Le jeton tient le bail : le bail est renouvelé, et la boîte rendue."""
    with ballet_state.locked(state):
        config = read_config(state)
        if config["lease"]["owner"] != owner:
            raise MaestroError("this session is not Maestro anymore: " + _who_holds(config["lease"]))
        box = _checked_mailbox(config)
        config["lease"] = {**config["lease"], "renewed": _now()}
        write_config(config, state)
    return box


def _consume_unread(box, orca):
    """Le non-lu de la boîte, consommé d'un coup, sans attendre."""
    answer = json.loads(orca(["orchestration", "check", "--terminal", box["terminal"], "--run", box["run"], "--json"]))
    return answer["result"]["messages"]


def _runs_of(box):
    return [box["run"], *([box["previous_run"]] if box.get("previous_run") else [])]


def _latest(history):
    return sorted(history, key=lambda message: message["sequence"])[-RECAP_LIMIT:]


def _history_of(run, orca):
    """Les derniers messages d'une Run de boîte, lus ou non (l'historique ne consomme rien)."""
    answer = json.loads(orca(["orchestration", "inbox", "--terminal", f"run:{run}", "--limit", str(RECAP_LIMIT), "--full", "--json"]))
    return [message for message in answer["result"]["messages"] if message["run_id"] == run]


def _forget_previous_run(state):
    with ballet_state.locked(state):
        config = read_config(state)
        if config["mailbox"].pop("previous_run", None):
            write_config(config, state)


def _render_messages(messages, state):
    config = read_config(state)
    return "\n\n".join(_message_text(message, config, state) for message in messages)


def _render_history(messages, unread_ids, state):
    if not messages:
        return "the mailbox is empty"
    config = read_config(state)
    unread = sum(1 for message in messages if message.get("id") in unread_ids)
    shown = "\n\n".join(_message_text(message, config, state, tag="unread" if message.get("id") in unread_ids else "read")
                         for message in messages)
    return f"{len(messages)} message(s), {unread} unread until now:\n\n{shown}"


def _message_text(message, config, state, tag=""):
    sender = message.get("from") or message.get("from_handle", "?")
    head = f"[{message.get('priority', 'normal')}] {message.get('type', 'message')} from {sender}"
    when = f" · {message['created_at']}" if message.get("created_at") else ""
    return (f"{head}{when}{' · ' + tag if tag else ''}\nSubject: {message.get('subject', '')}\n"
            f"{_body_with_decisions(message, config, state)}").rstrip()


def _body_with_decisions(message, config, state):
    """Le corps du message ; sous chaque élément d'un `status` `· ready` du Monitor, la décision de la règle de lancement ;
    sous un `· finished`, celle de fermer le Conductor."""
    import ballet_monitor
    body = message.get("body", "")
    finished = FINISHED_SUBJECT.match(message.get("subject", ""))
    if message.get("type") == "status" and finished:
        return f"{body}\nDECISION: {close_decision(finished.group(1), _terminal_named(body), state)}"
    project = ballet_monitor.project_of_ready_subject(message.get("subject", ""))
    if message.get("type") != "status" or not project:
        return body
    lines = []
    for line in body.splitlines():
        lines.append(line)
        item = ballet_monitor.READY_LINE.match(line)
        if item:
            lines.append(f"DECISION: {_decision(project, item.group('type'), config, state, item.group('number'))}")
    return "\n".join(lines)


def close_decision(key, terminal, state=None):
    """`close` quand le Conductor signalé est toujours fini, lancé par Maestro, dans le même terminal ; sinon
    `ask the Director (<raison>)`. C'est ici que cela se décide : l'agent ne fait que relayer le verdict."""
    line = ballet_conductors.read(state).get(key)
    if not line:
        return f"ask the Director ({key} is not in the registry anymore)"
    current = ballet_conductors.state_of(line)
    if current != ballet_conductors.FINISHED:
        return f"ask the Director ({key} is {current} now, not finished)"
    if not line.get("kind"):
        return f"ask the Director (Maestro did not launch {key}: its terminal is the Director's)"
    if line["terminal"] != terminal:
        return f"ask the Director ({key} now runs in {line['terminal']}, not {terminal})"
    return "close"


def close_delay_minutes(config):
    """`[conductors] close_finished_after_minutes` : un entier, 0 ou plus ; 10 sans la clé."""
    value = config.get("conductors", {}).get("close_finished_after_minutes", DEFAULT_CLOSE_MINUTES)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MaestroError(f"[conductors] close_finished_after_minutes in {CONFIG_NAME} must be a whole number, 0 or more, not {value!r}")
    return value


def _terminal_named(body):
    found = TERMINAL_IN_BODY.search(body)
    return found.group(1) if found else ""


# --- les sessions d'un projet -----------------------------------------------------


def sessions_of(home):
    """Les sessions ouvertes d'un projet, Rehearsal puis Workshop, lues avec les fonctions de leurs scripts. Ces
    scripts importent celui-ci : l'import se fait ici, pas en tête. Un projet sans `.ballet/run/` n'a aucune session
    (et rien n'y est créé). Chacune : (élément, Rehearsal courante, état)."""
    import ballet_rehearsal
    import ballet_workshop
    if not (home / ballet_rehearsal.RUN_DIR).is_dir():
        return []
    rehearsals = [(session.item, session.current or "-", _rehearsal_state(session, home))
                  for session in ballet_rehearsal.open_sessions(home)]
    workshops = [(workshop.item, "Workshop", workshop.status) for workshop in ballet_workshop.open_workshops(home)]
    return rehearsals + workshops


def _rehearsal_state(session, home):
    """L'état de la Rehearsal en cours (open, escalated…) ; celui de la session tant qu'aucune n'est lisible."""
    import ballet_rehearsal
    try:
        return ballet_rehearsal.load(session.current, home).status if session.current else session.status
    except ballet_rehearsal.RehearsalError:
        return session.status


def _conductor_lines(registry, orca):
    """Un Conductor par ligne : élément, genre, état, terminal et s'il vit, dernier événement, URL Remote Control. Un
    Conductor fini dont le terminal est fermé n'est plus que de l'histoire : il n'est pas montré."""
    if not registry:
        return []
    alive = _live_terminals_or_none(orca)
    lines = []
    for key, line in sorted(registry.items()):
        terminal = _terminal_state(line["terminal"], alive)
        if ballet_conductors.state_of(line) in (ballet_conductors.FINISHED, ballet_conductors.GONE, ballet_conductors.CLOSED) and terminal == "gone":
            continue
        last = f"last: {line['event']}" if line.get("event") else "no event yet"
        lines.append("  ".join(part for part in (key, line.get("kind") or "?", ballet_conductors.state_of(line),
                                                  f"{line['terminal']} ({terminal})", last, line.get("url", "")) if part))
    return lines


def _closing_rule(config):
    try:
        minutes = close_delay_minutes(config)
    except MaestroError as error:
        return str(error)
    return f"finished ones closed after {minutes} min" if minutes else "finished ones never closed"


def _live_terminals_or_none(orca):
    """Les terminaux vivants ; `None` quand Orca ne répond pas : `status` le dit au lieu d'échouer."""
    try:
        return live_terminals(orca)
    except (MaestroError, json.JSONDecodeError):
        return None


def _terminal_state(handle, alive):
    return "state unknown" if alive is None else "alive" if handle in alive else "gone"


def _session_line(alias, session, registry):
    item, rehearsal, state = session
    terminal = registry.get(f"{alias}#{item.lstrip('#')}", {}).get("terminal", "no terminal known")
    return f"{alias}  {item}  {rehearsal}  {state}  {terminal}"


# --- maestro.toml -------------------------------------------------------------


def read_config(state=None):
    """L'état de Maestro, avec ses trois tables toujours présentes (le bail avec ses trois clés) ; pas de fichier, un état vide."""
    path = _config_path(state)
    config = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    config.setdefault("mailbox", {})
    saved = config.get("lease", {})
    config["lease"] = {key: saved.get(key, empty) for key, empty in EMPTY_LEASE.items()}
    config.setdefault("projects", {})
    return config


def write_config(config, state=None):
    """Écrit l'état d'un coup, par un fichier temporaire puis un renommage."""
    ballet_state.write_atomically(_config_path(state), to_toml(config))


def to_toml(config):
    """Un TOML lisible : les valeurs simples d'une table, puis ses sous-tables, chacune sous son en-tête."""
    return HEADER + "\n".join(_table_lines(config, ())).lstrip("\n") + "\n"


def _table_lines(table, path):
    lines = [f"{_key(key)} = {_value(value)}" for key, value in table.items() if not isinstance(value, dict)]
    for key, sub in table.items():
        if isinstance(sub, dict):
            sub_path = (*path, key)
            if not sub or any(not isinstance(value, dict) for value in sub.values()):
                lines += ["", f"[{'.'.join(_key(part) for part in sub_path)}]"]
            lines += _table_lines(sub, sub_path)
    return lines


def _key(key):
    return key if BARE_KEY.match(key) else json.dumps(key, ensure_ascii=False)


def _value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)   # une chaîne JSON est une chaîne de base TOML
    if isinstance(value, list):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    raise MaestroError(f"cannot write {type(value).__name__} in {CONFIG_NAME}")


def _config_path(state=None):
    return ballet_state.state_dir(state) / CONFIG_NAME


# --- Orca ---------------------------------------------------------------------


def _terminal_alive(handle, orca):
    """Le terminal vit-il encore dans Orca ? Une Orca injoignable lève : on ne recrée jamais une boîte à l'aveugle."""
    return handle in live_terminals(orca)


def live_terminals(orca):
    """Les terminaux ouverts dans Orca. Une Orca injoignable lève."""
    return set(_texts(json.loads(orca(["terminal", "list", "--json"]))))


def _replace_terminal(config, orca, state):
    """Un nouveau terminal vide pour la boîte, noté aussitôt (avant sa Run) : un appel qui échoue ensuite le retrouve."""
    previous_run = config["mailbox"].get("run")
    receipt = json.loads(orca(["terminal", "create", "--title", MAILBOX_TITLE, "--json"]))
    terminal = first_id(receipt, "term_", "orca terminal create")
    config["mailbox"] = {"terminal": terminal, **({"previous_run": previous_run} if previous_run else {})}
    write_config(config, state)
    return config["mailbox"]


def _new_run(terminal, orca):
    receipt = json.loads(orca(["orchestration", "run-create", "--objective", MAILBOX_OBJECTIVE, "--from", terminal, "--json"]))
    return first_id(receipt, "run_", "orca orchestration run-create")


def first_id(receipt, prefix, command):
    found = next((text for text in _texts(receipt) if text.startswith(prefix)), None)
    if not found:
        raise MaestroError(f"{command} returned no {prefix}… id: {json.dumps(receipt)[:300]}")
    return found


def _texts(value):
    """Toutes les chaînes d'un reçu JSON d'Orca, où qu'elles soient."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _texts(item)
    elif isinstance(value, list):
        for item in value:
            yield from _texts(item)


def run_orca(arguments):
    completed = subprocess.run([os.environ.get("ORCA_CLI_COMMAND", "orca"), *arguments], capture_output=True, text=True)
    if completed.returncode != 0:
        raise MaestroError(completed.stderr.strip() or completed.stdout.strip() or "orca failed")
    return completed.stdout


# --- ligne de commande --------------------------------------------------------


def main(argv, orca=None):
    """Affiche le résultat et sort avec 0 ; 1 si Maestro ne peut pas le faire, 2 sur un usage invalide."""
    try:
        print(_command(argv[1:], orca or run_orca))
    except UsageError as error:
        print(error, file=sys.stderr)
        return 2
    except (MaestroError, OSError, tomllib.TOMLDecodeError, json.JSONDecodeError) as error:
        print(f"maestro: {error}", file=sys.stderr)
        return 1
    return 0


def _command(arguments, orca):
    if arguments == ["mailbox"]:
        return mailbox(orca)
    if arguments == ["monitor"]:
        return monitor(orca)
    if arguments == ["maestro"]:
        return maestro(orca)
    if arguments[:2] == ["project", "add"] and len(arguments) == 4:
        return add_project(arguments[2], arguments[3])
    if arguments == ["project", "list"]:
        return list_projects()
    if arguments in (["claim"], ["claim", "--take-over"]):
        return claim(take_over="--take-over" in arguments)
    if arguments[:2] == ["wait", "--owner"] and len(arguments) == 3:
        with _stopped_by_take_over():
            return wait(arguments[2], orca)
    if arguments[:2] == ["recap", "--owner"] and len(arguments) == 3:
        return recap(arguments[2], orca)
    if arguments == ["status"]:
        return status(orca)
    if arguments == ["ready"]:
        return ready()
    if arguments == ["pause"]:
        return pause()
    if arguments == ["resume"]:
        return resume()
    if arguments[:1] == ["tell"] and len(arguments) >= 3:
        return tell(arguments[1], " ".join(arguments[2:]), orca)
    raise UsageError(USAGE)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
