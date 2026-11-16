import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_rehearsal  # noqa: E402

PROFILE = """[project]
specs = "specs/"

[repos.antimurphy]
path = "."
proof = "pnpm proof"
"""

PLANNED_ISSUE = "## Context\n\n- [ ] not a task\n\n## Plan\n\n### Decisions\n\n- a.\n\n### antimurphy\n\nProof: `pnpm proof`\n\n- [ ] [C1] Do it.\n"
UNPLANNED_ISSUE = "## Context\n\n- [ ] a checkbox outside the plan\n\n## Plan\n\n<!-- empty -->\n"


def message(sender, to, kind, body, round_=1):
    header = {"ballet": "message", "from": sender, "to": to, "type": kind, "subject": "#3", "round": round_}
    return f"{json.dumps(header)}\n\n{body}\n"


def pull_request_state(verdict="APPROVED", checks=True):
    return {
        "headRefName": "rehearsal/FEAT-001.2",
        "reviews": [{"author": {"login": "b"}, "body": f"VERDICT: {verdict}", "submittedAt": "2026-11-16T12:00:00Z"}],
        "commits": [{"committedDate": "2026-11-16T11:00:00Z"}],
        "statusCheckRollup": [{"__typename": "CheckRun", "name": "proof", "status": "COMPLETED", "conclusion": "SUCCESS"}] if checks else [],
    }


class FakeWorld:
    """gh, git et orca, avec juste ce que le Conductor lit ; chaque commande est notée."""

    def __init__(self, issue_body=PLANNED_ISSUE, home="/home"):
        self.issue_body = issue_body
        self.home = home
        self.pull_request = pull_request_state()
        self.commands = []
        self.dispatches = 0
        self.reviews = [{"id": 11, "submitted_at": "2026-11-16T10:00:00Z", "html_url": "u", "body": "VERDICT: REJECTED\n\n## Blocking\n\n1. `a.rs:1` (inline comment)\n"}]
        self.threads = [{"id": "T1", "isResolved": False, "comments": {"nodes": [
            {"body": "**Blocking 1** — x", "path": "a.rs", "line": 1, "startLine": None, "pullRequestReview": {"databaseId": 11}}]}}]

    def __call__(self, argv):
        self.commands.append(argv)
        tool, arguments = argv[0], argv[1:]
        if tool == "gh":
            return self.gh(arguments)
        if tool == "git" and "worktree" in arguments:
            return f"worktree {self.home}\nbranch refs/heads/main\n\nworktree /wt/FEAT-001.2\nbranch refs/heads/rehearsal/FEAT-001.2\n"
        if arguments[:2] == ["orchestration", "worker-start"]:
            self.dispatches += 1
            return json.dumps({"ok": True, "result": {"worker": {"dispatchId": f"ctx_{self.dispatches}"}}})
        return ""

    def gh(self, arguments):
        if arguments[:2] == ["issue", "view"]:
            return json.dumps({"title": "FEAT-001.2 · Inventory model", "body": self.issue_body})
        if arguments[:2] == ["pr", "create"]:
            return "https://github.com/o/r/pull/8\n"
        if arguments[:2] == ["pr", "view"]:
            return json.dumps(self.pull_request)
        if arguments[:2] == ["api", "graphql"]:
            if any("reviewThreads" in argument for argument in arguments):
                return json.dumps({"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": self.threads}}}}})
            return "{}"
        if arguments[0] == "api" and arguments[1].endswith("/reviews") and "--input" not in arguments:
            return json.dumps([self.reviews])
        if arguments[0] == "api" and arguments[1].endswith("/comments") and "--method" not in arguments:
            return json.dumps([[]])
        if arguments[0] == "api":
            return "{}"
        return ""

    def ran(self, *prefix):
        return [command for command in self.commands if command[:len(prefix)] == list(prefix)]

    def started_roles(self):
        return [command[command.index("--task-title") + 1] for command in self.ran("orca", "orchestration", "worker-start")]


class BalletRehearsalTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        (self.home / ".ballet").mkdir()
        (self.home / ".ballet" / "config.toml").write_text(PROFILE, encoding="utf-8")
        environment = mock.patch.dict("os.environ", {"ORCA_CLI_COMMAND": "orca"})
        environment.start()
        self.addCleanup(environment.stop)
        self.world = FakeWorld(home=str(self.home))
        self.tools = ballet_rehearsal.Tools(run=self.world)

    def begin(self):
        return ballet_rehearsal.begin("#3", self.home, self.tools)

    def receive(self, text, question_id=None):
        path = self.home / "incoming.md"
        path.write_text(text, encoding="utf-8")
        return ballet_rehearsal.receive("FEAT-001.2", path, question_id, self.home, self.tools)

    def state(self):
        return json.loads((self.home / ".ballet" / "run" / "FEAT-001.2.json").read_text())

    def to_the_critic(self):
        self.begin()
        self.receive(message("dancer", "conductor", "report", "- Tasks: all done."))

    # --- begin ---

    def test_ouvre_le_worktree_depuis_main_et_lance_le_dancer_quand_le_plan_existe(self):
        step = self.begin()
        self.assertEqual(step.next, "wait")
        self.assertTrue(self.world.ran("git", "-C", str(self.home.resolve()), "fetch", "origin", "main"))
        create = self.world.ran("orca", "worktree", "create")[0]
        self.assertEqual(create[create.index("--branch") + 1], "rehearsal/FEAT-001.2")
        self.assertEqual(create[create.index("--base-branch") + 1], "origin/main")
        start = self.world.ran("orca", "orchestration", "worker-start")[0]
        self.assertEqual(start[start.index("--worktree") + 1], "path:/wt/FEAT-001.2")
        self.assertEqual(start[start.index("--model") + 1], "sonnet")
        self.assertEqual(self.world.started_roles(), ["Dancer · FEAT-001.2"])
        self.assertEqual(self.state()["dispatches"], {"dancer": "ctx_1"})

    def test_lance_le_choreographer_quand_l_issue_n_a_pas_de_taches(self):
        self.world.issue_body = UNPLANNED_ISSUE
        self.begin()
        self.assertEqual(self.world.started_roles(), ["Choreographer · FEAT-001.2"])

    def test_la_spec_du_worker_nomme_son_skill_et_le_protocole(self):
        self.begin()
        spec_file = self.world.ran("orca", "orchestration", "worker-start")[0]
        spec = Path(spec_file[spec_file.index("--spec-file") + 1]).read_text()
        self.assertIn("/ballet:dancer", spec)
        self.assertIn("orca orchestration ask", spec)
        self.assertIn("worker_done", spec)

    def test_refuse_d_ouvrir_deux_fois_la_meme_rehearsal(self):
        self.begin()
        with self.assertRaises(ballet_rehearsal.RehearsalError):
            self.begin()

    def test_refuse_de_demarrer_sans_profil_valide(self):
        (self.home / ".ballet" / "config.toml").write_text("[project]\n", encoding="utf-8")
        with self.assertRaisesRegex(ballet_rehearsal.RehearsalError, "init-project"):
            self.begin()

    # --- le Dancer rend son rapport ---

    def test_au_rapport_du_dancer_pousse_ouvre_la_pr_publie_le_rapport_et_lance_le_critic(self):
        self.to_the_critic()
        self.assertTrue(self.world.ran("git", "-C", str(self.home.resolve()), "push", "--set-upstream", "origin", "rehearsal/FEAT-001.2"))
        self.assertTrue(self.world.ran("gh", "pr", "create"))
        comment = self.world.ran("gh", "pr", "comment")[0]
        self.assertIn("- Tasks: all done.", comment[comment.index("--body") + 1])
        self.assertEqual(self.world.started_roles(), ["Dancer · FEAT-001.2", "Critic · FEAT-001.2"])
        self.assertEqual(self.state()["pull_request"], "8")

    # --- questions et réponses ---

    def test_porte_la_question_au_choreographer_puis_rend_la_reponse_au_dancer(self):
        self.begin()
        self.receive(message("dancer", "choreographer", "question", "1. Which name?"), question_id="msg_42")
        self.assertTrue(self.world.ran("gh", "issue", "comment"))
        self.assertEqual(self.world.started_roles()[-1], "Choreographer · FEAT-001.2")
        step = self.receive(message("choreographer", "dancer", "answer", "1. `Stock`."))
        reply = self.world.ran("orca", "orchestration", "reply")[0]
        self.assertEqual(reply[reply.index("--id") + 1], "msg_42")
        self.assertIn("1. `Stock`.", reply[reply.index("--body") + 1])
        self.assertEqual(len(self.world.ran("gh", "issue", "comment")), 2)
        self.assertEqual((step.next, self.state()["pending"]), ("wait", []))

    def test_une_seconde_question_va_au_choreographer_deja_lance_dans_sa_session(self):
        self.begin()
        self.receive(message("dancer", "choreographer", "question", "1. A?"), question_id="msg_1")
        self.receive(message("choreographer", "dancer", "answer", "1. B."))
        self.receive(message("dancer", "choreographer", "question", "1. C?", round_=2), question_id="msg_2")
        send = self.world.ran("orca", "orchestration", "send")[0]
        self.assertEqual(send[send.index("--to") + 1], "dispatch:ctx_2")
        self.assertEqual(len(self.world.started_roles()), 2)

    def test_escalade_au_dela_du_plafond_de_tours(self):
        self.begin()
        step = self.receive(message("dancer", "choreographer", "question", "1. Again?", round_=4), question_id="msg_9")
        self.assertEqual(step.next, "escalate")
        self.assertIn("max_exchange_rounds", step.reason)
        self.assertEqual(self.state()["status"], "escalated")

    def test_une_question_au_director_escalade(self):
        self.begin()
        step = self.receive(message("dancer", "director", "question", "1. Touch the CI?"), question_id="msg_3")
        self.assertEqual(step.next, "escalate")

    def test_une_question_sans_identifiant_orca_escalade(self):
        self.begin()
        self.assertEqual(self.receive(message("dancer", "choreographer", "question", "1. A?")).next, "escalate")

    def test_un_message_invalide_escalade_sans_rien_publier(self):
        self.begin()
        step = self.receive("not a message\n")
        self.assertEqual(step.next, "escalate")
        self.assertFalse(self.world.ran("gh", "issue", "comment"))

    # --- verdicts ---

    def test_un_refus_publie_la_review_et_renvoie_le_dancer_dans_sa_session(self):
        self.to_the_critic()
        step = self.receive(message("critic", "conductor", "verdict", "VERDICT: REJECTED\n\n## Blocking\n\n1. Fix."))
        self.assertTrue(self.world.ran("gh", "api"))
        send = self.world.ran("orca", "orchestration", "send")[0]
        self.assertEqual(send[send.index("--to") + 1], "dispatch:ctx_1")
        self.assertIn("read-pr 8", send[send.index("--body") + 1])
        self.assertEqual((step.next, self.state()["round_trips"]), ("wait", 1))

    def test_le_second_tour_du_critic_reprend_sa_session(self):
        self.to_the_critic()
        self.receive(message("critic", "conductor", "verdict", "VERDICT: REJECTED"))
        self.receive(message("dancer", "conductor", "report", "- Fixed.", round_=2))
        sends = self.world.ran("orca", "orchestration", "send")
        self.assertEqual(sends[-1][sends[-1].index("--to") + 1], "dispatch:ctx_2")
        self.assertEqual(len(self.world.ran("gh", "pr", "create")), 1)

    def test_chaque_verdict_met_a_jour_le_commentaire_des_verdicts(self):
        self.to_the_critic()
        self.receive(message("critic", "conductor", "verdict", "VERDICT: REJECTED"))
        posts = [c for c in self.world.ran("gh", "api") if c[2].endswith("/issues/8/comments") and "POST" in c]
        self.assertEqual(len(posts), 1)
        self.assertIn("| 1 | REJECTED | 1 |", next(a for a in posts[0] if a.startswith("body=")))

    def test_au_rapport_suivant_resout_les_fils_que_le_dancer_a_corriges(self):
        self.to_the_critic()
        self.receive(message("critic", "conductor", "verdict", "VERDICT: REJECTED"))
        step = self.receive(message("dancer", "conductor", "report", "- Outcome: done\n\n## Fixed\n\n- Blocking 1: abc1234", round_=2))
        resolutions = [c for c in self.world.ran("gh", "api", "graphql") if any("resolveReviewThread" in a for a in c)]
        self.assertEqual(len(resolutions), 1)
        self.assertIn("threads resolved: Blocking 1", step.done)

    def test_escalade_au_dela_du_plafond_d_allers_retours(self):
        self.to_the_critic()
        for _ in range(2):
            self.receive(message("critic", "conductor", "verdict", "VERDICT: REJECTED"))
            self.receive(message("dancer", "conductor", "report", "- Fixed."))
        step = self.receive(message("critic", "conductor", "verdict", "VERDICT: REJECTED"))
        self.assertEqual(step.next, "escalate")
        self.assertIn("max_round_trips", step.reason)

    def test_approved_merge_par_rebase_et_range_le_worktree(self):
        self.to_the_critic()
        step = self.receive(message("critic", "conductor", "verdict", "VERDICT: APPROVED"))
        self.assertEqual(step.next, "done")
        self.assertEqual(self.world.ran("gh", "pr", "merge")[0], ["gh", "pr", "merge", "8", "--rebase"])
        self.assertTrue(self.world.ran("orca", "worktree", "rm", "--worktree", "path:/wt/FEAT-001.2"))
        self.assertEqual(self.state()["status"], "done")

    def test_approved_sans_ci_escalade_et_ne_merge_pas(self):
        self.world.pull_request = pull_request_state(checks=False)
        self.to_the_critic()
        step = self.receive(message("critic", "conductor", "verdict", "VERDICT: APPROVED"))
        self.assertEqual(step.next, "escalate")
        self.assertIn("no CI", step.reason)
        self.assertFalse(self.world.ran("gh", "pr", "merge"))

    def test_premiere_retente_le_merge_une_fois_la_ci_verte(self):
        self.world.pull_request = pull_request_state(checks=False)
        self.to_the_critic()
        self.receive(message("critic", "conductor", "verdict", "VERDICT: APPROVED"))
        self.world.pull_request = pull_request_state()
        self.assertEqual(ballet_rehearsal.premiere("FEAT-001.2", self.home, self.tools).next, "done")

    def test_le_critic_qui_escalade_arrete_la_rehearsal(self):
        self.to_the_critic()
        step = self.receive(message("critic", "conductor", "verdict", "VERDICT: ESCALATE\n\n## Escalation\n\nScope."))
        self.assertEqual(step.next, "escalate")
        self.assertFalse(self.world.ran("gh", "pr", "merge"))

    # --- ligne de commande ---

    def test_la_derniere_ligne_dit_au_conductor_quoi_faire(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = ballet_rehearsal.main(["x", "begin", "3"], home=self.home, tools=self.tools)
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue().strip().splitlines()[-1], "NEXT: wait")


if __name__ == "__main__":
    unittest.main()
