"""Le seul point de passage vers GitHub : une liste fermée d'opérations sur les issues et les PR.

    python3 ballet_github.py read    <issue>                     # affiche le corps de l'issue
    python3 ballet_github.py publish <brouillon.md>              # crée l'issue, affiche son numéro
    python3 ballet_github.py plan    <issue> <plan.md>           # écrit la section ## Plan de l'issue
    python3 ballet_github.py slice   <parente> <brouillon.md>    # crée l'issue d'une slice, liée à sa parente
    python3 ballet_github.py read-pr <pr>                        # affiche la PR, ses reviews et ses commentaires, dans l'ordre
    python3 ballet_github.py push    <rehearsal/ID>              # pousse la branche de Rehearsal
    python3 ballet_github.py open-pr <issue> <rehearsal/ID>      # ouvre la PR sur main, liée à l'issue, affiche son numéro
    python3 ballet_github.py review  <pr> <verdict.md>           # publie le verdict du Critic : une review, un commentaire par point situé
    python3 ballet_github.py comment-issue <issue> <message.md>  # publie un message entre rôles sur l'issue
    python3 ballet_github.py comment-pr    <pr> <message.md>     # publie un message (rapport du Dancer) sur la PR
    python3 ballet_github.py verdicts <pr>                       # réécrit le commentaire « Verdicts » de la PR : une ligne par tour
    python3 ballet_github.py resolve  <pr> <rapport.md>          # résout les fils des points que le Dancer dit corrigés
    python3 ballet_github.py label   <pr> <VERDICT>              # pose le libellé du verdict (ballet:approved…), retire les autres
    python3 ballet_github.py merge   <pr>                        # la Premiere : merge par rebase, puis supprime la branche
    python3 ballet_github.py close   <issue> <pr>                # ferme l'issue livrée, puis sa parente si plus aucune slice n'est ouverte

Le repo GitHub est celui du dossier courant (celui que `gh` déduit du remote).
Le titre d'une issue est le premier titre `# …` de son brouillon ; le corps, tout le reste.
Un message (review, commentaire) suit `templates/message.md` : en-tête JSON sur la première ligne, publié en entier.
`review` poste chaque point qui commence par `fichier:ligne` (ou `fichier:début-fin`), sur une ligne du diff,
en commentaire sur cette ligne ; le corps de la review garde le verdict, la preuve et les autres points.
`resolve` lit la section `## Fixed` du rapport (`- Blocking 1: <sha>`, ``- Note `fichier:ligne`: <sha>``),
répond « Fixed in <sha> » dans le fil du dernier verdict, puis le marque résolu.
Le verdict qui fait foi est le libellé de la PR : `ballet:approved`, `ballet:rejected` ou `ballet:escalated`.
Le Conductor pose celui du Critic ; le Director tranche une escalade en posant le sien. S'il en reste plusieurs,
le dernier posé l'emporte. La review du Critic et le commentaire « Verdicts » restent, pour la lecture.
`merge` refuse sans libellé `ballet:approved` posé après le dernier commit, et sans CI entièrement verte.
`close` ne se fie pas au `Closes #N` de la PR (implicite, et absent d'une PR ouverte à la main) : il ferme lui-même.
Une slice se reconnaît à sa première ligne, `Part of #<parente>` (posée par `slice`).
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from ballet_message import VERDICT_LINE, MessageError, read_message

PLAN_HEADING = "## Plan"
PARENT_LINE = re.compile(r"^Part of #(\d+)\s*$", re.MULTILINE)
BASE_BRANCH = "main"
REHEARSAL_BRANCH = re.compile(r"rehearsal/(FEAT|BUG|TASK)-\d{3}(\.\d+)?")
VERDICTS_MARKER = "<!-- ballet:verdicts -->"
FIXED_POINT = re.compile(r"^- (Blocking (\d+)|Note `([^`:]+):(\d+)(?:-\d+)?`)\s*(?::|—|–|-)\s*`?([0-9a-f]{7,40})`?", re.MULTILINE)
REVIEW_THREADS = """query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) { pullRequest(number: $number) { reviewThreads(first: 100) { nodes {
    id isResolved comments(first: 1) { nodes { body path line startLine pullRequestReview { databaseId } } }
  } } } }
}"""
REPLY_TO_THREAD = "mutation($thread: ID!, $body: String!) { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $thread, body: $body}) { comment { id } } }"
RESOLVE_THREAD = "mutation($thread: ID!) { resolveReviewThread(input: {threadId: $thread}) { thread { id } } }"
GREEN_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
LIST_ITEM = re.compile(r"^(?:(\d+)\.|-)\s+(.*)$")
PLACED_POINT = re.compile(r"^`([^`\s]+?):(\d+)(?:-(\d+))?`\s*(?:—|–|-|:)?\s*(.*)$")
HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
VERDICT_LABELS = {
    "APPROVED": ("ballet:approved", "0e8a16", "Ballet: approved, the Premiere may merge"),
    "REJECTED": ("ballet:rejected", "d93f0b", "Ballet: rejected, back to the Dancer"),
    "ESCALATE": ("ballet:escalated", "fbca04", "Ballet: escalated, the Director decides"),
}


class GitHubError(Exception):
    """Une opération est refusée, ou `gh` a échoué."""


def read_issue(number, run=None):
    return _issue_body(number, run or _run_gh)


def publish_issue(draft_path, run=None):
    title, body = _title_and_body(_read_draft(draft_path))
    return _create_issue(title, body, run or _run_gh)


def write_plan(number, plan_path, run=None):
    run = run or _run_gh
    body = _issue_body(number, run)
    plan = _plan_only(_read_draft(plan_path))
    _edit_issue(number, _with_plan(body, plan), run)


def publish_slice(parent_number, draft_path, run=None):
    title, body = _title_and_body(_read_draft(draft_path))
    return _create_issue(title, _linked_to_parent(body, parent_number), run or _run_gh)


def read_pull_request(number, run=None):
    number = _issue_number(number)
    pull_request = _pull_request(number, run or _run_gh)
    return _as_markdown(number, pull_request)


def push_branch(branch, git=None):
    _push(_rehearsal_branch(branch), git or _run_git)


def open_pull_request(issue_number, branch, run=None):
    run = run or _run_gh
    number = _issue_number(issue_number)
    title = _issue_title(number, run)
    return _create_pull_request(title, f"Closes #{number}\n", _rehearsal_branch(branch), run)


def publish_review(pr_number, verdict_path, run=None):
    run = run or _run_gh
    number = _issue_number(pr_number)
    header, text = _read_message(verdict_path)
    _require_verdict(header, text)
    commentable = _commentable_lines(_pull_request_diff(number, run))
    body, comments = _split_into_line_comments(text, commentable)
    _post_review(number, body, comments, run)


def comment_issue(issue_number, message_path, run=None):
    _, text = _read_message(message_path)
    (run or _run_gh)(["issue", "comment", _issue_number(issue_number), "--body", text])


def comment_pull_request(pr_number, message_path, run=None):
    _, text = _read_message(message_path)
    (run or _run_gh)(["pr", "comment", _issue_number(pr_number), "--body", text])


def update_verdicts(pr_number, run=None):
    run = run or _run_gh
    number = _issue_number(pr_number)
    rounds = _verdict_rounds(_api_list(f"repos/{{owner}}/{{repo}}/pulls/{number}/reviews", run))
    body = _verdicts_table(rounds)
    existing = _verdicts_comment_id(number, run)
    if existing:
        run(["api", f"repos/{{owner}}/{{repo}}/issues/comments/{existing}", "--method", "PATCH", "-f", f"body={body}"])
    else:
        run(["api", f"repos/{{owner}}/{{repo}}/issues/{number}/comments", "--method", "POST", "-f", f"body={body}"])


def resolve_fixed(pr_number, report_path, run=None):
    """Renvoie les points résolus et ceux dont aucun fil ouvert du dernier verdict ne correspond."""
    run = run or _run_gh
    number = _issue_number(pr_number)
    _, text = _read_message(report_path)
    fixed = _fixed_points(text)
    if not fixed:
        return [], []
    last_review = _verdict_rounds(_api_list(f"repos/{{owner}}/{{repo}}/pulls/{number}/reviews", run))[-1]["id"]
    threads = _open_threads(number, last_review, run)
    resolved, unmatched = [], []
    for point in fixed:
        thread = next((thread for thread in threads if _matches(point, thread)), None)
        if thread:
            _close_thread(thread["id"], f"Fixed in {point['sha']} (Dancer).", run)
            resolved.append(point["label"])
        else:
            unmatched.append(point["label"])
    return resolved, unmatched


def merge_pull_request(pr_number, run=None, git=None):
    run = run or _run_gh
    number = _issue_number(pr_number)
    pull_request = _merge_state(number, run)
    _require_fresh_approval(pull_request, _verdict_labels_in_force(number, run))
    _require_green_ci(pull_request)
    run(["pr", "merge", number, "--rebase"])
    _delete_remote_branch(pull_request["headRefName"], git or _run_git)


def close_issue(issue_number, pr_number, run=None):
    """Ferme l'issue livrée par la PR, puis sa parente quand c'était sa dernière slice ouverte ; renvoie ce qui a été fermé."""
    run = run or _run_gh
    number, pr_number = _issue_number(issue_number), _issue_number(pr_number)
    issue = _issue_state(number, run)
    closed = _close_if_open(number, issue, f"Done in #{pr_number}.", run)
    parent = _parent_of(issue["body"])
    if parent and not _open_slices(parent, besides=number, run=run):
        closed += _close_if_open(parent, _issue_state(parent, run), f"All its slices are done; the last one, #{number}, in #{pr_number}.", run)
    return closed


def label_pull_request(pr_number, verdict, run=None):
    """Pose le libellé du verdict sur la PR et retire les deux autres : un seul verdict en vigueur."""
    run = run or _run_gh
    number = _issue_number(pr_number)
    verdict = _known_verdict(verdict)
    _ensure_verdict_labels(run)
    run(["pr", "edit", number, *_label_changes(verdict)])


def director_decision(pr_number, run=None):
    """Le verdict en vigueur (dernier libellé posé), sa date, et les commentaires de la PR depuis la dernière escalade."""
    run = run or _run_gh
    number = _issue_number(pr_number)
    events = _label_events(number, run)
    verdict, labeled_at = _latest_verdict(_labels_in_force(events))
    escalated_at = _last_labeled(events, "ESCALATE")
    return {"verdict": verdict, "labeled_at": labeled_at, "escalated_at": escalated_at,
            "comments": _comments_since(number, escalated_at, run)}


def pull_request_status(pr_number, run=None):
    """Où en est la PR : son état GitHub, le verdict de son libellé, celui du Critic et sa CI, sans rien refuser."""
    run = run or _run_gh
    number = _issue_number(pr_number)
    pull_request = _merge_state(number, run)
    in_force, _ = _latest_verdict(_verdict_labels_in_force(number, run))
    return {"state": pull_request.get("state", ""), "label": in_force and _label_name(in_force), "verdict": _verdict_or_none(pull_request),
            "ci": _ci_summary(pull_request)}


def main(argv):
    operation, arguments = (argv[1], argv[2:]) if len(argv) > 1 else (None, [])
    try:
        result = _dispatch(operation, arguments)
    except GitHubError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    if result is not None:
        print(result)
    return 0


# --- opérations -------------------------------------------------------------


def _dispatch(operation, arguments):
    operations = {
        "read": (read_issue, 1),
        "publish": (publish_issue, 1),
        "plan": (write_plan, 2),
        "slice": (publish_slice, 2),
        "read-pr": (read_pull_request, 1),
        "push": (push_branch, 1),
        "open-pr": (open_pull_request, 2),
        "review": (publish_review, 2),
        "comment-issue": (comment_issue, 2),
        "comment-pr": (comment_pull_request, 2),
        "verdicts": (update_verdicts, 1),
        "resolve": (_resolve_and_say, 2),
        "label": (label_pull_request, 2),
        "merge": (merge_pull_request, 1),
        "close": (_close_and_say, 2),
    }
    if operation not in operations:
        raise GitHubError(f"unknown operation '{operation}'; known: {', '.join(operations)}")
    function, arity = operations[operation]
    if len(arguments) != arity:
        raise GitHubError(f"{operation} expects {arity} argument(s)")
    return function(*arguments)


def _close_and_say(issue_number, pr_number):
    closed = close_issue(issue_number, pr_number)
    return "closed: " + (", ".join(f"#{number}" for number in closed) or "nothing, already closed")


def _issue_state(number, run):
    return json.loads(run(["issue", "view", number, "--json", "state,body"]))


def _close_if_open(number, issue, comment, run):
    if issue["state"] != "OPEN":
        return []
    run(["issue", "close", number, "--reason", "completed", "--comment", comment])
    return [number]


def _parent_of(body):
    match = PARENT_LINE.match(body)
    return match.group(1) if match else None


def _open_slices(parent, besides, run):
    """Les slices encore ouvertes de la parente ; la recherche GitHub est floue, la première ligne tranche.
    L'index de recherche a du retard : la slice qu'on vient de fermer peut y paraître encore ouverte."""
    found = json.loads(run(["issue", "list", "--state", "open", "--search", f'"Part of #{parent}" in:body',
                            "--json", "number,body", "--limit", "100"]))
    return [issue["number"] for issue in found if _parent_of(issue["body"]) == parent and str(issue["number"]) != besides]


def _issue_body(number, run):
    output = run(["issue", "view", _issue_number(number), "--json", "body"])
    return json.loads(output)["body"]


def _pull_request(number, run):
    output = run(["pr", "view", number, "--json", "title,body,comments"])
    pull_request = json.loads(output)
    pull_request["reviews"] = _api_list(f"repos/{{owner}}/{{repo}}/pulls/{number}/reviews", run)
    pull_request["line_comments"] = _api_list(f"repos/{{owner}}/{{repo}}/pulls/{number}/comments", run)
    return pull_request


def _api_list(path, run):
    pages = json.loads(run(["api", path, "--paginate", "--slurp"]))
    return [item for page in pages for item in page]


def _pull_request_diff(number, run):
    return run(["pr", "diff", number])


def _post_review(number, body, comments, run):
    review = {"body": body, "event": "COMMENT", "comments": comments}
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as payload:
        json.dump(review, payload)
    try:
        run(["api", f"repos/{{owner}}/{{repo}}/pulls/{number}/reviews", "--method", "POST", "--input", payload.name])
    finally:
        Path(payload.name).unlink()


def _issue_title(number, run):
    output = run(["issue", "view", number, "--json", "title"])
    return json.loads(output)["title"]


def _merge_state(number, run):
    output = run(["pr", "view", number, "--json", "state,headRefName,reviews,commits,statusCheckRollup"])
    return json.loads(output)


def _create_pull_request(title, body, branch, run):
    url = run(["pr", "create", "--base", BASE_BRANCH, "--head", branch, "--title", title, "--body", body]).strip()
    return url.rsplit("/", 1)[-1]


def _push(branch, git):
    git(["push", "--set-upstream", "origin", branch])


def _delete_remote_branch(branch, git):
    git(["push", "origin", "--delete", _rehearsal_branch(branch)])


def _create_issue(title, body, run):
    url = run(["issue", "create", "--title", title, "--body", body]).strip()
    return url.rsplit("/", 1)[-1]


def _edit_issue(number, body, run):
    run(["issue", "edit", _issue_number(number), "--body", body])


# --- résumé des verdicts et fils de review ----------------------------------


def _resolve_and_say(pr_number, report_path):
    resolved, unmatched = resolve_fixed(pr_number, report_path)
    return f"resolved: {', '.join(resolved) or 'none'}; no open thread for: {', '.join(unmatched) or 'none'}"


def _verdict_rounds(reviews):
    """Les reviews qui portent un verdict, dans l'ordre : id, tour, verdict, points bloquants, date, lien."""
    rounds = []
    for review in sorted(reviews, key=lambda review: review.get("submitted_at") or ""):
        verdict = VERDICT_LINE.search(review.get("body") or "")
        if verdict:
            rounds.append({"id": review["id"], "round": _round_of(review["body"], len(rounds) + 1), "verdict": verdict.group(1),
                           "blocking": _blocking_count(review["body"]), "at": review["submitted_at"], "url": review.get("html_url", "")})
    if not rounds:
        raise GitHubError("the pull request has no verdict yet")
    return rounds


def _round_of(body, fallback):
    try:
        return int(json.loads(body.split("\n", 1)[0]).get("round", fallback))
    except (json.JSONDecodeError, AttributeError, ValueError):
        return fallback


def _blocking_count(body):
    section = body.split("## Blocking", 1)[1] if "## Blocking" in body else ""
    section = section.split("\n## ", 1)[0]
    return len(re.findall(r"^\d+\. ", section, re.MULTILINE))


def _verdicts_table(rounds):
    rows = "".join(f"| {r['round']} | {r['verdict']} | {r['blocking']} | {r['at']} | [review]({r['url']}) |\n" for r in rounds)
    return f"{VERDICTS_MARKER}\n### Verdicts\n\n| Round | Verdict | Blocking | At | |\n|---|---|---|---|---|\n{rows}"


def _verdicts_comment_id(number, run):
    comments = _api_list(f"repos/{{owner}}/{{repo}}/issues/{number}/comments", run)
    return next((comment["id"] for comment in comments if (comment.get("body") or "").startswith(VERDICTS_MARKER)), None)


def _fixed_points(text):
    section = text.split("## Fixed", 1)[1] if "## Fixed" in text else ""
    section = section.split("\n## ", 1)[0]
    return [
        {"label": match.group(1), "blocking": match.group(2), "path": match.group(3),
         "line": int(match.group(4)) if match.group(4) else None, "sha": match.group(5)}
        for match in FIXED_POINT.finditer(section)
    ]


def _open_threads(number, review_id, run):
    output = run(["api", "graphql", "-f", f"query={REVIEW_THREADS}", "-F", "owner={owner}", "-F", "name={repo}", "-F", f"number={number}"])
    nodes = json.loads(output)["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    return [
        {"id": node["id"], **node["comments"]["nodes"][0]}
        for node in nodes
        if not node["isResolved"] and node["comments"]["nodes"]
        and (node["comments"]["nodes"][0].get("pullRequestReview") or {}).get("databaseId") == review_id
    ]


def _matches(point, thread):
    if point["blocking"]:
        return thread["body"].startswith(f"**Blocking {point['blocking']}**")
    return (thread["body"].startswith("**Note**") and thread["path"] == point["path"]
            and point["line"] in (thread.get("line"), thread.get("startLine")))


def _close_thread(thread_id, reply, run):
    run(["api", "graphql", "-f", f"query={REPLY_TO_THREAD}", "-f", f"thread={thread_id}", "-f", f"body={reply}"])
    run(["api", "graphql", "-f", f"query={RESOLVE_THREAD}", "-f", f"thread={thread_id}"])


# --- conditions de la Premiere ----------------------------------------------


def _require_fresh_approval(pull_request, labels):
    """Le libellé en vigueur doit être `ballet:approved`, posé après le dernier commit de la branche."""
    verdict, labeled_at = _latest_verdict(labels)
    if verdict != "APPROVED":
        raise GitHubError(f"the verdict label in force is {_label_name(verdict)}, not ballet:approved")
    last_commit = max(commit["committedDate"] for commit in pull_request["commits"])
    if labeled_at < last_commit:
        raise GitHubError(f"ballet:approved ({labeled_at}) is older than the last commit ({last_commit})")


def _last_verdict(pull_request):
    verdicts = [
        (review["submittedAt"], match.group(1))
        for review in pull_request.get("reviews", [])
        if (match := VERDICT_LINE.search(review["body"]))
    ]
    if not verdicts:
        raise GitHubError("the pull request has no verdict yet")
    return max(verdicts)


# --- libellés de verdict ----------------------------------------------------


def _known_verdict(verdict):
    verdict = verdict.upper()
    if verdict not in VERDICT_LABELS:
        raise GitHubError(f"unknown verdict '{verdict}'; known: {', '.join(VERDICT_LABELS)}")
    return verdict


def _ensure_verdict_labels(run):
    """Crée les trois libellés au premier usage ; `--force` les laisse tels quels ensuite."""
    for name, color, description in VERDICT_LABELS.values():
        run(["label", "create", name, "--color", color, "--description", description, "--force"])


def _label_changes(verdict):
    changes = ["--add-label", _label_name(verdict)]
    for other in VERDICT_LABELS:
        if other != verdict:
            changes += ["--remove-label", _label_name(other)]
    return changes


def _label_name(verdict):
    return VERDICT_LABELS[verdict][0] if verdict else "none"


def _verdict_labels_in_force(number, run):
    return _labels_in_force(_label_events(number, run))


def _label_events(number, run):
    """Les poses et retraits de libellés de verdict, dans l'ordre de la timeline de la PR."""
    names = {name: verdict for verdict, (name, _, _) in VERDICT_LABELS.items()}
    return [
        (event["event"], names[event["label"]["name"]], event["created_at"])
        for event in _api_list(f"repos/{{owner}}/{{repo}}/issues/{number}/timeline", run)
        if event.get("event") in ("labeled", "unlabeled") and event.get("label", {}).get("name") in names
    ]


def _labels_in_force(events):
    """Verdict → date de sa dernière pose, pour chaque libellé encore sur la PR."""
    in_force = {}
    for kind, verdict, at in events:
        if kind == "labeled":
            in_force[verdict] = at
        else:
            in_force.pop(verdict, None)
    return in_force


def _latest_verdict(labels):
    if not labels:
        return None, None
    verdict = max(labels, key=labels.get)
    return verdict, labels[verdict]


def _last_labeled(events, verdict):
    return max((at for kind, labeled, at in events if kind == "labeled" and labeled == verdict), default=None)


def _comments_since(number, since, run):
    if not since:
        return []
    comments = json.loads(run(["pr", "view", number, "--json", "comments"]))["comments"]
    return [comment["body"] for comment in comments if comment["createdAt"] > since]


def _verdict_or_none(pull_request):
    try:
        return _last_verdict(pull_request)[1]
    except GitHubError:
        return None


def _ci_summary(pull_request):
    try:
        _require_green_ci(pull_request)
    except GitHubError as error:
        return str(error)
    return "CI green"


def _require_green_ci(pull_request):
    checks = pull_request.get("statusCheckRollup") or []
    if not checks:
        raise GitHubError("no CI check on the pull request: a missing CI is not a green CI")
    not_green = [_check_name(check) for check in checks if not _is_green(check)]
    if not_green:
        raise GitHubError(f"CI not green: {', '.join(not_green)}")


def _is_green(check):
    if check.get("__typename") == "StatusContext":
        return check.get("state") == "SUCCESS"
    return check.get("status") == "COMPLETED" and check.get("conclusion") in GREEN_CONCLUSIONS


def _check_name(check):
    return check.get("name") or check.get("context") or "unnamed check"


# --- commentaires en ligne du verdict ---------------------------------------


def _commentable_lines(diff):
    """Les lignes du nouveau côté du diff, par fichier : celles où GitHub accepte un commentaire."""
    lines, path, current = {}, None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
            lines.setdefault(path, set())
        elif hunk := HUNK_HEADER.match(line):
            current = int(hunk.group(1))
        elif path and line[:1] in (" ", "+") and not line.startswith("+++"):
            lines[path].add(current)
            current += 1
    return lines


def _split_into_line_comments(text, commentable):
    """Sort du verdict chaque point situé dans le diff ; il y laisse un renvoi d'une ligne."""
    body, comments, section = [], [], None
    for point in _blocks(text):
        if point[0].startswith("## "):
            section = point[0][3:].strip()
        comment = _line_comment(point, section, commentable)
        if comment:
            comments.append(comment)
            body.append(_pointer(point[0]))
        else:
            body.extend(point)
    return "\n".join(body).rstrip() + "\n", comments


def _blocks(text):
    """Découpe le texte en blocs : un point de liste avec ses lignes indentées, ou une ligne seule."""
    blocks = []
    for line in text.splitlines():
        if blocks and line.startswith((" ", "\t")) and line.strip() and LIST_ITEM.match(blocks[-1][0]):
            blocks[-1].append(line)
        else:
            blocks.append([line])
    return blocks


def _line_comment(point, section, commentable):
    item = LIST_ITEM.match(point[0])
    placed = item and PLACED_POINT.match(item.group(2))
    if not placed:
        return None
    path, start, end, first_words = placed.group(1), int(placed.group(2)), int(placed.group(3) or placed.group(2)), placed.group(4)
    if not {start, end} <= commentable.get(path, set()):
        return None
    text = "\n".join([first_words] + [line.strip() for line in point[1:]])
    comment = {"path": path, "line": end, "side": "RIGHT", "body": f"**{_label(section, item.group(1))}** — {text}"}
    if start != end:
        comment = {"path": path, "start_line": start, "start_side": "RIGHT", **{k: comment[k] for k in ("line", "side", "body")}}
    return comment


def _label(section, number):
    if section == "Blocking":
        return f"Blocking {number}" if number else "Blocking"
    if section == "Notes":
        return "Note"
    return section or "Point"


def _pointer(first_line):
    item = LIST_ITEM.match(first_line)
    placed = PLACED_POINT.match(item.group(2))
    marker = f"{item.group(1)}." if item.group(1) else "-"
    place = f"{placed.group(1)}:{placed.group(2)}" + (f"-{placed.group(3)}" if placed.group(3) else "")
    return f"{marker} `{place}` (inline comment)"


# --- messages entre rôles ---------------------------------------------------


def _read_message(path):
    try:
        return read_message(path)
    except MessageError as error:
        raise GitHubError(str(error)) from error


def _require_verdict(header, text):
    if header.get("type") != "verdict":
        raise GitHubError(f"a review publishes a verdict, not a message of type '{header.get('type')}'")


# --- texte des issues -------------------------------------------------------


def _as_markdown(number, pull_request):
    header = f"# PR #{number} · {pull_request['title']}\n\n{pull_request['body'].strip()}\n"
    entries = sorted(_reviews(pull_request) + _comments(pull_request))
    return header + "".join(f"\n## {heading}\n\n{body.strip()}\n" for _, heading, body in entries)


def _reviews(pull_request):
    return [
        (review["submitted_at"], f"Review · {review['user']['login']} · {review['submitted_at']}",
         review["body"] + _line_comments_of(review["id"], pull_request))
        for review in pull_request.get("reviews", [])
        if review.get("submitted_at")
    ]


def _line_comments_of(review_id, pull_request):
    return "".join(
        f"\n\n### `{comment['path']}:{_lines_of(comment)}`\n\n{comment['body'].strip()}"
        for comment in pull_request.get("line_comments", [])
        if comment.get("pull_request_review_id") == review_id
    )


def _lines_of(comment):
    line = comment.get("line") or comment.get("original_line")
    start = comment.get("start_line") or comment.get("original_start_line")
    return f"{start}-{line}" if start and start != line else f"{line}"


def _comments(pull_request):
    return [
        (comment["createdAt"], f"Comment · {comment['author']['login']} · {comment['createdAt']}", comment["body"])
        for comment in pull_request.get("comments", [])
    ]


def _read_draft(path):
    path = Path(path)
    if not path.is_file():
        raise GitHubError(f"file not found: {path}")
    return path.read_text(encoding="utf-8")


def _title_and_body(text):
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# "):
            body = "\n".join(lines[index + 1:]).strip() + "\n"
            return line[2:].strip(), body
    raise GitHubError("the draft has no `# …` title; a file holding only the ## Plan section goes to `plan`")


def _plan_only(text):
    if any(line.startswith("# ") for line in text.splitlines()):
        raise GitHubError("this is a full issue draft (`# …` title); `plan` expects only the ## Plan section, a draft goes to `publish` or `slice`")
    return text


def _with_plan(body, plan):
    """Remplace le contenu de la section ## Plan, jusqu'au titre ## suivant."""
    lines = body.splitlines()
    if PLAN_HEADING not in lines:
        raise GitHubError(f"the issue has no '{PLAN_HEADING}' section")
    start = lines.index(PLAN_HEADING) + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    section = ["", _without_plan_heading(plan).strip(), ""]
    return "\n".join(lines[:start] + section + lines[end:]).rstrip() + "\n"


def _without_plan_heading(plan):
    lines = plan.strip().splitlines()
    return "\n".join(lines[1:]) if lines and lines[0].strip() == PLAN_HEADING else plan


def _linked_to_parent(body, parent_number):
    return f"Part of #{_issue_number(parent_number)}\n\n{body}"


# --- gh ---------------------------------------------------------------------


def _issue_number(value):
    number = str(value).lstrip("#")
    if not number.isdigit():
        raise GitHubError(f"invalid issue or PR number: {value}")
    return number


def _rehearsal_branch(branch):
    if not REHEARSAL_BRANCH.fullmatch(branch):
        raise GitHubError(f"not a Rehearsal branch: {branch} (expected rehearsal/FEAT-NNN, rehearsal/FEAT-NNN.K, BUG-NNN or TASK-NNN)")
    return branch


def _run_git(arguments):
    completed = subprocess.run(["git", *arguments], capture_output=True, text=True)
    if completed.returncode != 0:
        raise GitHubError(completed.stderr.strip() or f"git {arguments[0]} failed")
    return completed.stdout


def _run_gh(arguments):
    completed = subprocess.run(["gh", *arguments], capture_output=True, text=True)
    if completed.returncode != 0:
        raise GitHubError(completed.stderr.strip() or f"gh {arguments[0]} failed")
    return completed.stdout


if __name__ == "__main__":
    sys.exit(main(sys.argv))
