"""Orca vu par les Conductors : ouvrir un worktree, lancer un worker, lire un message de la boîte d'Orca.

Les deux Conductors (`ballet_rehearsal.py` pour la Rehearsal, `ballet_workshop.py` pour le Workshop) parlent à Orca de
la même façon ; ce module est ce qu'ils ont en commun. Il ne décide rien : une aide qui ne trouve pas ce qu'elle
cherche rend `None`, et son appelant choisit l'erreur qu'il en fait.

`tools` est ce que les Conductors passent partout : `tools.git(repo)` et `tools.orca(arguments)` renvoient la sortie
de la commande.
"""

import json

WORKER_MESSAGES = ("worker_done", "question", "escalation")


def open_worktree(repo, branch, tools, issue=""):
    """Crée le worktree de la branche, depuis `origin/main`, et rend son chemin (`None` si Orca ne l'a pas créé)."""
    git = tools.git(repo)
    git(["fetch", "origin", "main"])
    linked = ["--issue", issue] if issue else []
    tools.orca(["worktree", "create", "--name", branch.replace("/", "-").replace(".", "-"),
                "--repo", f"path:{repo}", "--base-branch", "origin/main", "--branch", branch,
                *linked, "--no-parent", "--json"])
    return _worktree_of(branch, git(["worktree", "list", "--porcelain"]))


def start_worker(spec_path, worktree, agent, title, tools, model=""):
    """Lance un worker sur sa mission, dans le worktree, et rend son dispatch (`None` si le reçu n'en nomme pas)."""
    arguments = ["orchestration", "worker-start", "--spec-file", str(spec_path), "--worktree", f"path:{worktree}",
                 "--agent", agent, "--task-title", title, "--json"]
    if model:
        arguments += ["--model", model]
    return find_key(json.loads(tools.orca(arguments)), "dispatchId")


def inbox_message(wanted, by, tools):
    """Le message entier, retrouvé dans la boîte d'Orca par son id (`by="message"`) ou comme le dernier du dispatch
    d'un worker (`by="dispatch"`) ; `None` s'il n'y est pas."""
    inbox = json.loads(tools.orca(["orchestration", "inbox", "--limit", "200", "--full", "--json"]))
    messages = find_list(inbox, "messages")
    return _by_id(messages, wanted) if by == "message" else _latest_from(messages, wanted)


def run_messages(run_id, tools):
    """Les messages en attente du Run du Conductor, dans l'ordre d'arrivée, consommés d'un coup : Orca les marque lus,
    sans acquittement (vérifié sur Orca 1.4.259, spike 0002). Seul le terminal du Conductor peut consommer sa boîte :
    la commande part de ses outils, dans son terminal (`ORCA_TERMINAL_HANDLE`)."""
    return find_list(json.loads(tools.orca(["orchestration", "check", "--run", run_id, "--json"])), "messages")


def worker_dispatch(message):
    """Le dispatch du worker qui a envoyé le message, lu dans son payload ; vide pour un message qui n'en vient pas."""
    return payload(message).get("dispatchId") or ""


def worker_role(message, dispatches, handles):
    """Le rôle du worker qui a écrit le message, vide s'il n'est pas l'un des siens (`dispatches` et `handles` : rôle → dispatch,
    rôle → handle). Orca rouvre un worker qui a fini sous un nouveau dispatch à chaque message qu'on lui envoie (vu sur
    FEAT-009, Orca 1.4.259) : le dispatch ne suffit pas. On le reconnaît donc à son dispatch, sinon à son handle, qui ne change
    pas, sinon à la signature Ballet d'un rôle qui a un worker ici et dont le handle connu n'est pas un autre."""
    dispatch, handle = worker_dispatch(message), worker_handle(message)
    found = _key_of(dispatches, dispatch) or _key_of(handles, handle)
    if found:
        return found
    signed = ballet_sender(message)
    if signed in dispatches and dispatches[signed] and (not handle or handles.get(signed, "") in ("", handle)):
        return signed
    return ""


def worker_handle(message):
    """Le handle stable du worker qui écrit (`structworker_…`) ; vide pour un message écrit au nom d'un dispatch, d'un Run
    ou d'un terminal (une question posée par `ask`, le réveil de la mutation)."""
    handle = message.get("from_handle") or ""
    return "" if handle.startswith(("dispatch:", "run:", "term_")) else handle


def ballet_sender(message):
    """Le rôle qui signe le message Ballet (le `from` de sa ligne d'en-tête), vide sans en-tête Ballet."""
    first = (message.get("body") or "").split("\n", 1)[0]
    try:
        header = json.loads(first)
    except json.JSONDecodeError:
        return ""
    return header.get("from", "") if isinstance(header, dict) and header.get("ballet") == "message" else ""


def payload(message):
    """Orca rend le payload en JSON dans une chaîne, ou déjà décodé, ou pas du tout."""
    found = message.get("payload")
    if isinstance(found, str):
        try:
            found = json.loads(found)
        except json.JSONDecodeError:
            return {}
    return found if isinstance(found, dict) else {}


def find_key(value, key):
    """La première valeur texte de `key`, où qu'elle soit dans un reçu JSON d'Orca."""
    if isinstance(value, dict):
        if isinstance(value.get(key), str):
            return value[key]
        value = list(value.values())
    if isinstance(value, list):
        return next((found for item in value if (found := find_key(item, key))), None)
    return None


def find_list(value, key):
    if isinstance(value, dict):
        if isinstance(value.get(key), list):
            return value[key]
        return next((found for item in value.values() if (found := find_list(item, key))), [])
    return []


def _worktree_of(branch, porcelain):
    path = None
    for line in porcelain.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):]
        elif line == f"branch refs/heads/{branch}":
            return path
    return None


def _key_of(mapping, value):
    return next((key for key, known in mapping.items() if value and known == value), "")


def _by_id(messages, message_id):
    return next((message for message in messages if message.get("id") == message_id), None)


def _latest_from(messages, dispatch_id):
    sent = [message for message in messages
            if message.get("type") in WORKER_MESSAGES and worker_dispatch(message) == dispatch_id]
    return max(sent, key=lambda message: int(message.get("sequence") or 0), default=None)
