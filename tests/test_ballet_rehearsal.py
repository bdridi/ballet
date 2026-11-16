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


RUNNING_CHECK = {"__typename": "CheckRun", "name": "proof", "status": "IN_PROGRESS", "conclusion": ""}
FAILED_CHECK = {"__typename": "CheckRun", "name": "proof", "status": "COMPLETED", "conclusion": "FAILURE"}


def pull_request_state(verdict="APPROVED", checks=True):
    return {
        "headRefName": "rehearsal/FEAT-001.2",
        "reviews": [{"author": {"login": "b"}, "body": f"VERDICT: {verdict}", "submittedAt": "2026-11-16T12:00:00Z"}],
        "commits": [{"committedDate": "2026-11-16T11:00:00Z"}],
        "statusCheckRollup": [{"__typename": "CheckRun", "name": "proof", "status": "COMPLETED", "conclusion": "SUCCESS"}] if checks else [],
        "comments": [],
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
        self.timeline = []
        self.issue_state = "OPEN"
        self.numstat = "10\t2\tsrc/a.rs\n"
        self.inbox = []
        self.branch = "rehearsal/FEAT-001.2"
        self.head = "c0ffee1"
        self.dirty = ""
        self.changed = []
        self.new_commits = []
        self.threads = [{"id": "T1", "isResolved": False, "comments": {"nodes": [
            {"body": "**Blocking 1** — x", "path": "a.rs", "line": 1, "startLine": None, "pullRequestReview": {"databaseId": 11}}]}}]

    def __call__(self, argv):
        self.commands.append(argv)
        tool, arguments = argv[0], argv[1:]
        if tool == "gh":
            return self.gh(arguments)
        if tool == "git" and "push" in arguments:
            self.pull_request["commits"] = [{"committedDate": f"2026-11-16T12:{len(self.timeline):02d}:00Z"}]
            return ""
        if tool == "git" and "--numstat" in arguments:
            return self.numstat
        if tool == "git" and "worktree" in arguments:
            return f"worktree {self.home}\nbranch refs/heads/main\n\nworktree /wt/FEAT-001.2\nbranch refs/heads/rehearsal/FEAT-001.2\n"
        if tool == "git":
            return self.policy_git(arguments[2:])
        if arguments[:2] == ["orchestration", "inbox"]:
            return json.dumps({"ok": True, "result": {"messages": self.inbox}})
        if arguments[:2] == ["orchestration", "worker-start"]:
            self.dispatches += 1
            return json.dumps({"ok": True, "result": {"worker": {"dispatchId": f"ctx_{self.dispatches}"}}})
        return ""

    def policy_git(self, arguments):
        """Ce que lit la politique : un worktree en règle, sauf ce que le test y met (`changed`, `dirty`, `branch`)."""
        answers = {
            ("rev-parse", "--abbrev-ref"): self.branch + "\n",
            ("rev-parse", "HEAD"): self.head + "\n",
            ("rev-list", "--count"): "0\n",
            ("status", "--porcelain"): self.dirty,
            ("merge-base", "origin/main"): "base\n",
            ("diff", "--name-only"): "\n".join(self.changed),
        }
        if arguments[0] == "rev-list" and arguments[1] != "--count":
            return "\n".join(self.new_commits)
        return answers.get(tuple(arguments[:2]), "")

    def gh(self, arguments):
        if arguments[:2] == ["issue", "view"]:
            return json.dumps({"title": "FEAT-001.2 · Inventory model", "body": self.issue_body, "state": self.issue_state})
        if arguments[:2] == ["issue", "list"]:
            return "[]"
        if arguments[:2] == ["pr", "create"]:
            return "https://github.com/o/r/pull/8\n"
        if arguments[:2] == ["pr", "view"] and arguments[-1] == "labels":
            return json.dumps({"labels": [{"name": name} for name in sorted(self.labels())]})
        if arguments[:2] == ["pr", "view"]:
            return json.dumps(self.pull_request)
        if arguments[:2] == ["pr", "edit"]:
            self.relabel(arguments)
            return ""
        if arguments[0] == "api" and arguments[1].endswith("/timeline"):
            return json.dumps([self.timeline])
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

    def relabel(self, arguments):
        """Comme GitHub : `--add-label` d'un libellé déjà posé, ou `--remove-label` d'un libellé absent,
        ne laisse aucune trace dans la timeline."""
        on_the_pr = self.labels()
        for flag, label in zip(arguments, arguments[1:]):
            if flag == "--add-label" and label not in on_the_pr:
                self.label_event("labeled", label)
            elif flag == "--remove-label" and label in on_the_pr:
                self.label_event("unlabeled", label)

    def label_event(self, kind, label):
        at = f"2026-11-16T12:{len(self.timeline):02d}:00Z"
        self.timeline.append({"event": kind, "label": {"name": label}, "created_at": at})
        return at

    def labels(self):
        on_the_pr = set()
        for event in self.timeline:
            (on_the_pr.add if event["event"] == "labeled" else on_the_pr.discard)(event["label"]["name"])
        return on_the_pr

    def director_comments(self, *bodies):
        self.pull_request["comments"] = [{"body": body, "createdAt": "2026-11-16T13:00:00Z"} for body in bodies]

    def ran(self, *prefix):
        return [command for command in self.commands if command[:len(prefix)] == list(prefix)]

    def started_roles(self):
        return [command[command.index("--task-title") + 1] for command in self.ran("orca", "orchestration", "worker-start")]


STRICT_PROFILE = PROFILE + "\n[escalation]\nmax_diff_lines = 100\nmax_diff_strict = true\n"
OVERSIZED_NUMSTAT = "150\t30\tsrc/inventory.rs\n900\t0\tCargo.lock\n-\t-\tlogo.png\n"


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
        self.sleeps = []
        self.tools = ballet_rehearsal.Tools(run=self.world, sleep=self.sleeps.append)

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

    def escalated(self):
        self.to_the_critic()
        self.receive(message("critic", "conductor", "verdict", "VERDICT: ESCALATE\n\n## Escalation\n\nSize."))

    def resume(self):
        return ballet_rehearsal.resume("FEAT-001.2", self.home, self.tools)

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

    # --- le journal de ce que le Conductor remet aux workers ---

    def handoffs(self):
        return [(entry["role"], entry["how"], entry["dispatch"]) for entry in self.journal("handoff")]

    def test_begin_ouvre_le_journal_puis_journalise_le_lancement_du_premier_role(self):
        self.begin()
        events = [json.loads(line)["event"] for line in (self.home / ".ballet" / "run" / "journal.jsonl").read_text().splitlines()]
        self.assertEqual(events[:2], ["begin", "handoff"])
        self.assertEqual(self.journal("begin"), [{}])
        start = self.journal("handoff")[0]
        self.assertEqual((start["role"], start["how"], start["dispatch"], start["agent"], start["model"]),
                         ("dancer", "start", "ctx_1", "claude", "sonnet"))
        self.assertIn("Execute your repo's section of the plan of issue #3", start["text"])

    def test_un_role_deja_lance_relance_dans_sa_session_est_journalise(self):
        self.to_the_critic()
        self.receive(message("critic", "conductor", "verdict", "VERDICT: REJECTED\n\n## Blocking\n\n1. Fix."))
        self.assertEqual(self.handoffs(), [("dancer", "start", "ctx_1"), ("critic", "start", "ctx_2"), ("dancer", "send", "ctx_1")])
        self.assertIn("read-pr 8", self.journal("handoff")[-1]["text"])

    def test_la_question_portee_et_la_reponse_rendue_sont_journalisees(self):
        self.begin()
        self.receive(message("dancer", "choreographer", "question", "1. Which name?"), question_id="msg_42")
        self.receive(message("choreographer", "dancer", "answer", "1. `Stock`."))
        self.assertEqual(self.handoffs(), [("dancer", "start", "ctx_1"), ("choreographer", "start", "ctx_2"), ("dancer", "reply", "ctx_1")])
        self.assertIn("1. Which name?", self.journal("handoff")[1]["text"])
        self.assertIn("1. `Stock`.", self.journal("handoff")[2]["text"])

    def test_la_relance_sans_worker_done_est_un_passage_journalise(self):
        self.begin()
        self.stopped("msg_stop")
        nudge = self.journal("handoff")[-1]
        self.assertEqual((nudge["role"], nudge["how"], nudge["text"]), ("dancer", "nudge", ballet_rehearsal.REPORT_REMINDER))
        self.assertEqual(self.journal("nudge"), [])

    def test_chaque_message_recu_est_journalise_avec_son_texte_entier(self):
        self.begin()
        text = message("dancer", "conductor", "report", "- Tasks: all done.")
        self.receive(text)
        logged = self.journal("message")[0]
        self.assertEqual((logged["from"], logged["type"], logged["text"]), ("dancer", "report", text))

    # --- le Dancer rend son rapport ---

    def test_au_rapport_du_dancer_pousse_ouvre_la_pr_publie_le_rapport_et_lance_le_critic(self):
        self.to_the_critic()
        self.assertTrue(self.world.ran("git", "-C", str(self.home.resolve()), "push", "--set-upstream", "origin", "rehearsal/FEAT-001.2"))
        self.assertTrue(self.world.ran("gh", "pr", "create"))
        comment = self.world.ran("gh", "pr", "comment")[0]
        self.assertIn("- Tasks: all done.", comment[comment.index("--body") + 1])
        self.assertEqual(self.world.started_roles(), ["Dancer · FEAT-001.2", "Critic · FEAT-001.2"])
        self.assertEqual(self.state()["pull_request"], "8")

    # --- la politique ---

    def policy_events(self):
        journal = (self.home / ".ballet" / "run" / "journal.jsonl").read_text().splitlines()
        return [json.loads(line)["detail"] for line in journal if json.loads(line)["event"] == "policy"]

    def test_chaque_passage_est_verifie_et_journalise_meme_en_regle(self):
        self.to_the_critic()
        self.assertEqual(self.policy_events(), [{"role": "dancer", "violations": []}])

    def test_un_dancer_en_violation_n_est_pas_pousse_et_corrige_une_fois(self):
        self.begin()
        self.world.changed = ["specs/backlog.md"]
        step = self.receive(message("dancer", "conductor", "report", "- Done."))
        self.assertEqual(step.next, "wait")
        self.assertFalse(self.world.ran("git", "-C", str(self.home.resolve()), "push", "--set-upstream", "origin", "rehearsal/FEAT-001.2"))
        self.assertFalse(self.world.ran("gh", "pr", "create"))
        send = self.world.ran("orca", "orchestration", "send")[-1]
        self.assertIn("- specs/backlog.md: the specs space", send[send.index("--body") + 1])

    def test_la_deuxieme_violation_escalade(self):
        self.begin()
        self.world.changed = ["specs/backlog.md"]
        self.receive(message("dancer", "conductor", "report", "- Done."))
        step = self.receive(message("dancer", "conductor", "report", "- Done again."))
        self.assertEqual((step.next, step.reason), ("escalate", "policy: the dancer broke the rules: specs/backlog.md: the specs space"))

    def test_une_violation_corrigee_repart_vers_le_critic(self):
        self.begin()
        self.world.changed = [".github/workflows/proof.yml"]
        self.receive(message("dancer", "conductor", "report", "- Done."))
        self.world.changed = []
        self.receive(message("dancer", "conductor", "report", "- Reverted."))
        self.assertEqual(self.world.started_roles()[-1], "Critic · FEAT-001.2")

    def test_un_critic_qui_a_ecrit_escalade_sans_que_son_verdict_soit_publie(self):
        self.to_the_critic()
        self.world.head = "d1rty00"
        step = self.receive(message("critic", "conductor", "verdict", "VERDICT: APPROVED"))
        self.assertEqual(step.next, "escalate")
        self.assertIn("the Critic is read-only", step.reason)
        self.assertFalse(self.world.ran("gh", "pr", "merge"))

    def test_les_commits_du_choreographer_qui_repond_lui_appartiennent(self):
        self.begin()
        self.receive(message("dancer", "choreographer", "question", "1. A rule?"), question_id="msg_1")
        self.world.changed, self.world.new_commits = ["AGENTS.md"], ["abc1234"]
        self.receive(message("choreographer", "dancer", "answer", "1. Yes, in AGENTS.md."))
        self.assertEqual(self.state()["owned"], ["abc1234"])

    def test_un_choreographer_qui_repond_hors_de_ses_fichiers_escalade(self):
        self.begin()
        self.receive(message("dancer", "choreographer", "question", "1. A?"), question_id="msg_1")
        self.world.changed = ["src/a.rs"]
        step = self.receive(message("choreographer", "dancer", "answer", "1. Done for you."))
        self.assertEqual(step.next, "escalate")
        self.assertFalse(self.world.ran("orca", "orchestration", "reply"))

    def test_le_dramaturg_qui_repond_est_verifie_et_ses_specs_lui_appartiennent(self):
        self.begin()
        self.receive(message("dancer", "dramaturg", "question", "1. Empty stock?"), question_id="msg_1")
        self.world.changed, self.world.new_commits = ["specs/features/FEAT-001.md"], ["5bec5ec"]
        self.receive(message("dramaturg", "dancer", "answer", "1. Rectified in the feature."))
        self.assertEqual(self.state()["owned"], ["5bec5ec"])
        self.assertEqual(self.policy_events()[-1], {"role": "dramaturg", "violations": []})

    def test_un_dramaturg_qui_repond_dans_le_code_escalade(self):
        self.begin()
        self.receive(message("dancer", "dramaturg", "question", "1. A?"), question_id="msg_1")
        self.world.changed = ["src/a.rs"]
        self.assertEqual(self.receive(message("dramaturg", "dancer", "answer", "1. Done.")).next, "escalate")

    def test_le_plan_du_choreographer_est_verifie_avant_de_lancer_le_dancer(self):
        self.world.issue_body = UNPLANNED_ISSUE
        self.begin()
        self.world.changed = ["src/a.rs"]
        step = self.receive(message("choreographer", "conductor", "report", "- Plan written."))
        self.assertEqual((step.next, self.world.started_roles()), ("wait", ["Choreographer · FEAT-001.2"]))
        self.assertIn("src/a.rs: outside the choreographer's perimeter ([policy.roles.choreographer] writes, extra_writes)", step.done[0])

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

    def test_la_premiere_ferme_l_issue(self):
        self.to_the_critic()
        step = self.receive(message("critic", "conductor", "verdict", "VERDICT: APPROVED"))
        self.assertEqual(self.world.ran("gh", "issue", "close")[0][:4], ["gh", "issue", "close", "3"])
        self.assertIn("issues closed: #3", step.done)

    def test_une_issue_qu_on_ne_peut_fermer_n_annule_pas_la_premiere(self):
        self.to_the_critic()
        world = self.world
        def failing(argv):
            if argv[:3] == ["gh", "issue", "close"]:
                raise ballet_rehearsal.RehearsalError("HTTP 403")
            return world(argv)
        self.tools.run = failing
        step = self.receive(message("critic", "conductor", "verdict", "VERDICT: APPROVED"))
        self.assertEqual((step.next, self.state()["status"]), ("done", "done"))
        self.assertIn("issue #3 left open: HTTP 403; close it by hand", step.done)

    def test_approved_sans_ci_escalade_et_ne_merge_pas(self):
        self.world.pull_request = pull_request_state(checks=False)
        self.to_the_critic()
        step = self.receive(message("critic", "conductor", "verdict", "VERDICT: APPROVED"))
        self.assertEqual(step.next, "escalate")
        self.assertIn("no CI", step.reason)
        self.assertFalse(self.world.ran("gh", "pr", "merge"))
        self.assertIn("verdict APPROVED published on #8, labelled, Verdicts comment updated", step.done)

    def test_premiere_retente_le_merge_une_fois_la_ci_verte(self):
        self.world.pull_request = pull_request_state(checks=False)
        self.to_the_critic()
        self.receive(message("critic", "conductor", "verdict", "VERDICT: APPROVED"))
        self.world.pull_request = pull_request_state()
        self.assertEqual(ballet_rehearsal.premiere("FEAT-001.2", self.home, self.tools).next, "done")

    def test_une_ci_en_cours_est_attendue_puis_la_premiere_merge(self):
        self.world.pull_request["statusCheckRollup"] = [RUNNING_CHECK]
        self.to_the_critic()
        self.sleeps.clear()
        self.tools.sleep = lambda seconds: (self.sleeps.append(seconds), self.finish_ci() if len(self.sleeps) == 2 else None)
        step = self.receive(message("critic", "conductor", "verdict", "VERDICT: APPROVED"))
        self.assertEqual(step.next, "done")
        self.assertEqual(self.sleeps, [ballet_rehearsal.CI_POLL_SECONDS] * 2)
        self.assertIn("waited 30s for the CI", step.done)
        self.assertTrue(self.world.ran("gh", "pr", "merge"))

    def test_une_ci_qui_n_en_finit_pas_escalade_apres_ci_wait_seconds(self):
        self.world.pull_request["statusCheckRollup"] = [RUNNING_CHECK]
        self.to_the_critic()
        step = self.receive(message("critic", "conductor", "verdict", "VERDICT: APPROVED"))
        self.assertEqual(step.next, "escalate")
        self.assertIn("CI still running: proof", step.reason)
        self.assertIn("ci_wait_seconds", step.reason)
        self.assertEqual(sum(self.sleeps), 480)
        self.assertFalse(self.world.ran("gh", "pr", "merge"))
        self.assertIn("ballet:approved", self.world.labels())

    def test_une_ci_rouge_escalade_tout_de_suite_sans_attendre(self):
        self.world.pull_request["statusCheckRollup"] = [FAILED_CHECK, RUNNING_CHECK]
        self.to_the_critic()
        step = self.receive(message("critic", "conductor", "verdict", "VERDICT: APPROVED"))
        self.assertEqual(step.next, "escalate")
        self.assertIn("CI not green", step.reason)
        self.assertEqual(self.sleeps, [])

    def finish_ci(self):
        self.world.pull_request = pull_request_state()

    def test_le_critic_qui_escalade_arrete_la_rehearsal(self):
        self.to_the_critic()
        step = self.receive(message("critic", "conductor", "verdict", "VERDICT: ESCALATE\n\n## Escalation\n\nScope."))
        self.assertEqual(step.next, "escalate")
        self.assertFalse(self.world.ran("gh", "pr", "merge"))

    # --- libellés et décision du Director ---

    def test_chaque_verdict_pose_son_libelle_et_retire_les_autres(self):
        self.to_the_critic()
        self.receive(message("critic", "conductor", "verdict", "VERDICT: REJECTED"))
        self.assertEqual(self.world.labels(), {"ballet:rejected"})
        self.receive(message("dancer", "conductor", "report", "- Fixed."))
        self.receive(message("critic", "conductor", "verdict", "VERDICT: APPROVED"))
        self.assertEqual(self.world.labels(), {"ballet:approved"})

    def test_une_escalade_avec_une_pr_pose_ballet_escalated(self):
        self.to_the_critic()
        for _ in range(3):
            self.receive(message("critic", "conductor", "verdict", "VERDICT: REJECTED"))
            self.receive(message("dancer", "conductor", "report", "- Fixed."))
        step = self.receive(message("critic", "conductor", "verdict", "VERDICT: REJECTED"))
        self.assertEqual(step.next, "escalate")
        self.assertEqual(self.world.labels(), {"ballet:escalated"})

    def test_une_ci_en_cours_ne_retire_pas_l_approbation(self):
        self.world.pull_request = pull_request_state(checks=False)
        self.to_the_critic()
        self.receive(message("critic", "conductor", "verdict", "VERDICT: APPROVED"))
        self.assertEqual(self.world.labels(), {"ballet:approved"})

    def test_resume_sans_decision_reste_escalade(self):
        self.escalated()
        step = self.resume()
        self.assertEqual((step.next, self.state()["status"]), ("escalate", "escalated"))
        self.assertIn("nothing decided yet", step.reason)
        self.assertEqual(self.world.labels(), {"ballet:escalated"})

    def test_le_director_approuve_par_le_libelle_et_resume_fait_la_premiere(self):
        self.escalated()
        self.world.label_event("labeled", "ballet:approved")
        step = self.resume()
        self.assertEqual(step.next, "done")
        self.assertTrue(self.world.ran("gh", "pr", "merge"))
        self.assertTrue(self.world.ran("orca", "worktree", "rm"))
        self.assertEqual(self.state()["status"], "done")

    def test_la_decision_du_director_est_journalisee(self):
        self.escalated()
        self.world.label_event("labeled", "ballet:approved")
        self.resume()
        journal = (self.home / ".ballet" / "run" / "journal.jsonl").read_text().splitlines()
        decisions = [json.loads(line) for line in journal if '"director-decision"' in line]
        self.assertEqual(decisions[0]["detail"]["verdict"], "APPROVED")

    def test_une_approbation_du_director_sur_ci_en_cours_reste_posee(self):
        self.escalated()
        self.world.pull_request = pull_request_state(checks=False)
        self.world.label_event("labeled", "ballet:approved")
        step = self.resume()
        self.assertEqual(step.next, "escalate")
        self.assertIn("ballet:approved", self.world.labels())
        self.world.pull_request = pull_request_state()
        self.assertEqual(ballet_rehearsal.premiere("FEAT-001.2", self.home, self.tools).next, "done")

    def test_le_director_refuse_avec_un_commentaire_et_le_dancer_reprend(self):
        self.escalated()
        self.world.label_event("labeled", "ballet:rejected")
        self.world.director_comments("Make the fields of `Date` private.")
        step = self.resume()
        self.assertEqual((step.next, self.state()["status"]), ("wait", "open"))
        send = self.world.ran("orca", "orchestration", "send")[-1]
        self.assertEqual(send[send.index("--to") + 1], "dispatch:ctx_1")
        self.assertIn("> Make the fields of `Date` private.", send[send.index("--body") + 1])

    def test_un_refus_sans_commentaire_reste_escalade_sans_toucher_au_libelle(self):
        self.escalated()
        self.world.label_event("labeled", "ballet:rejected")
        step = self.resume()
        self.assertEqual(step.next, "escalate")
        self.assertIn("needs a comment", step.reason)
        self.assertIn("ballet:rejected", self.world.labels())

    def test_un_commentaire_d_avant_l_escalade_n_est_pas_une_decision(self):
        self.escalated()
        self.world.label_event("labeled", "ballet:rejected")
        self.world.pull_request["comments"] = [{"body": "Dancer report", "createdAt": "2026-11-16T09:00:00Z"}]
        self.assertIn("needs a comment", self.resume().reason)

    def test_resume_sur_une_rehearsal_ouverte_ne_fait_rien(self):
        self.begin()
        step = self.resume()
        self.assertEqual(step.next, "wait")
        self.assertFalse(self.world.ran("gh", "api"))

    # --- taille du diff ---

    def strict(self):
        (self.home / ".ballet" / "config.toml").write_text(STRICT_PROFILE, encoding="utf-8")
        self.world.numstat = OVERSIZED_NUMSTAT

    def journal(self, event):
        lines = (self.home / ".ballet" / "run" / "journal.jsonl").read_text().splitlines()
        return [json.loads(line)["detail"] for line in lines if json.loads(line)["event"] == event]

    def test_chaque_rapport_mesure_et_journalise_la_taille_meme_sous_le_seuil(self):
        self.to_the_critic()
        self.assertEqual(self.journal("diff-size"), [{"counted": 12, "excluded": 0, "excluded_files": [], "limit": 400,
                                                      "strict": False, "over": False, "round": 1}])
        diffs = [command[3:] for command in self.world.ran("git") if "--numstat" in command]
        self.assertEqual(diffs, [["diff", "--numstat", "origin/main...rehearsal/FEAT-001.2"]])

    def test_hors_mode_strict_un_gros_diff_est_marque_et_part_au_critic(self):
        self.world.numstat = "500\t0\tsrc/a.rs\n"
        self.begin()
        step = self.receive(message("dancer", "conductor", "report", "- Done."))
        self.assertEqual(step.next, "wait")
        self.assertIn("ballet:oversized", self.world.labels())
        self.assertIn("diff: 500 lines counted, 0 excluded, limit 400: over the limit, not blocking", step.done)
        self.assertEqual(len(self.world.started_roles()), 2)

    def test_en_mode_strict_un_gros_diff_escalade_avant_le_critic(self):
        self.strict()
        self.begin()
        step = self.receive(message("dancer", "conductor", "report", "- Done."))
        self.assertEqual(step.next, "escalate")
        self.assertIn("diff of 180 lines, over max_diff_lines (100)", step.reason)
        self.assertEqual(self.world.labels(), {"ballet:oversized", "ballet:escalated"})
        self.assertEqual(self.world.started_roles(), ["Dancer · FEAT-001.2"])
        self.assertEqual(self.journal("diff-size")[0]["excluded_files"], ["Cargo.lock"])

    def test_la_taille_acceptee_par_le_director_lance_le_critic(self):
        self.strict()
        self.begin()
        self.receive(message("dancer", "conductor", "report", "- Done."))
        self.world.label_event("labeled", "ballet:size-accepted")
        step = self.resume()
        self.assertEqual((step.next, self.state()["blocked_on"]), ("wait", ""))
        self.assertEqual(self.world.started_roles()[-1], "Critic · FEAT-001.2")

    def test_une_taille_deja_acceptee_ne_bloque_plus_au_tour_suivant(self):
        self.strict()
        self.begin()
        self.receive(message("dancer", "conductor", "report", "- Done."))
        self.world.label_event("labeled", "ballet:size-accepted")
        self.resume()
        self.receive(message("critic", "conductor", "verdict", "VERDICT: REJECTED"))
        self.assertEqual(self.receive(message("dancer", "conductor", "report", "- Fixed.")).next, "wait")

    def test_sans_decision_sur_la_taille_le_director_voit_l_option(self):
        self.strict()
        self.begin()
        self.receive(message("dancer", "conductor", "report", "- Done."))
        self.assertIn("ballet:size-accepted", self.resume().reason)

    def test_le_libelle_oversized_tombe_quand_le_diff_repasse_sous_le_seuil(self):
        self.world.numstat = "500\t0\tsrc/a.rs\n"
        self.to_the_critic()
        self.receive(message("critic", "conductor", "verdict", "VERDICT: REJECTED"))
        self.world.numstat = "50\t0\tsrc/a.rs\n"
        self.receive(message("dancer", "conductor", "report", "- Smaller."))
        self.assertNotIn("ballet:oversized", self.world.labels())

    def test_status_montre_la_derniere_mesure(self):
        self.to_the_critic()
        self.assertIn("- diff: 12 lines counted, 0 excluded, limit 400: within the limit", self.run_main("status", "FEAT-001.2")[1])

    # --- notes du Critic ---

    def critic_says(self, verdict, notes=""):
        notes_section = f"\n\n## Notes\n\n{notes}" if notes else ""
        return self.receive(message("critic", "conductor", "verdict", f"VERDICT: {verdict}\n\n## Blocking\n\nNone.{notes_section}"))

    def last_send_body(self):
        send = self.world.ran("orca", "orchestration", "send")[-1]
        return send[send.index("--to") + 1], send[send.index("--body") + 1]

    def test_approuve_avec_des_notes_le_dancer_les_prend_en_un_commit(self):
        self.to_the_critic()
        step = self.critic_says("APPROVED", "- `a.rs:1`: private fields.\n- Cache the key.")
        self.assertEqual(step.next, "wait")
        self.assertFalse(self.world.ran("gh", "pr", "merge"))
        to, body = self.last_send_body()
        self.assertEqual(to, "dispatch:ctx_1")
        self.assertIn("one single commit", body)
        self.assertIn("approved with 2 note(s): dancer asked to take them in one commit", step.done)

    def test_le_critic_ne_relit_que_le_commit_des_notes_puis_la_premiere(self):
        self.to_the_critic()
        self.critic_says("APPROVED", "- Cache the key.")
        self.receive(message("dancer", "conductor", "report", "- Notes taken.\n\n## Fixed\n\n- Note `a.rs:1`: abc1234", round_=2))
        to, body = self.last_send_body()
        self.assertEqual(to, "dispatch:ctx_2")
        self.assertIn("Notes round of pull request #8, round 2", body)
        step = self.critic_says("APPROVED", "- Another idea.")
        self.assertEqual(step.next, "done")
        self.assertEqual(self.state()["round_trips"], 0)

    def test_approuve_sans_note_merge_directement(self):
        self.to_the_critic()
        self.assertEqual(self.critic_says("APPROVED").next, "done")

    def test_un_refus_demande_les_notes_en_un_dernier_commit(self):
        self.to_the_critic()
        self.receive(message("critic", "conductor", "verdict", "VERDICT: REJECTED\n\n## Blocking\n\n1. Fix."))
        self.assertIn("then take its notes in one last commit", self.last_send_body()[1])

    # --- messages lus chez Orca ---

    def orca_message(self, message_id, kind, body, subject="s"):
        self.world.inbox.append({"id": message_id, "type": kind, "subject": subject, "body": body})

    def receive_from_orca(self, message_id):
        return ballet_rehearsal.receive_from_orca("FEAT-001.2", message_id, self.home, self.tools)

    def test_un_rapport_lu_chez_orca_par_son_id_ouvre_la_pr(self):
        self.begin()
        self.orca_message("msg_1", "worker_done", message("dancer", "conductor", "report", "- Done."))
        self.assertEqual(self.receive_from_orca("msg_1").next, "wait")
        self.assertTrue(self.world.ran("gh", "pr", "create"))

    def test_une_question_lue_chez_orca_garde_son_id_pour_la_reponse(self):
        self.begin()
        self.orca_message("msg_q", "question", message("dancer", "choreographer", "question", "1. A?"))
        self.receive_from_orca("msg_q")
        self.receive(message("choreographer", "dancer", "answer", "1. B."))
        reply = self.world.ran("orca", "orchestration", "reply")[0]
        self.assertEqual(reply[reply.index("--id") + 1], "msg_q")

    def test_un_reveil_qui_ne_nomme_que_le_dispatch_lit_son_dernier_message(self):
        self.begin()
        self.world.inbox += [
            {"id": "msg_q", "type": "question", "sequence": 1, "payload": json.dumps({"dispatchId": "ctx_1"}), "body": "{}"},
            {"id": "msg_other", "type": "worker_done", "sequence": 3, "payload": json.dumps({"dispatchId": "ctx_9"}), "body": "{}"},
            {"id": "msg_done", "type": "worker_done", "sequence": 2, "payload": json.dumps({"dispatchId": "ctx_1"}),
             "body": message("dancer", "conductor", "report", "- Done.")},
        ]
        code, lines = self.run_main("receive", "FEAT-001.2", "--dispatch", "ctx_1")
        self.assertEqual((code, lines[-1]), (0, "NEXT: wait"))
        self.assertTrue(self.world.ran("gh", "pr", "create"))

    def test_un_dispatch_sans_message_escalade(self):
        self.begin()
        step = ballet_rehearsal.receive_from_orca("FEAT-001.2", "ctx_nope", self.home, self.tools, by="dispatch")
        self.assertEqual((step.next, step.reason), ("escalate", "no Orca message from dispatch ctx_nope in the inbox"))

    def test_un_id_inconnu_escalade(self):
        self.begin()
        step = self.receive_from_orca("msg_nope")
        self.assertEqual((step.next, step.reason), ("escalate", "no Orca message msg_nope in the inbox"))

    def stopped(self, message_id, reason="finished", dispatch="ctx_1"):
        self.world.inbox.append({"id": message_id, "type": "escalation", "subject": "Worker stopped without reporting", "body": "Worker term_1 exited",
                                 "payload": json.dumps({"dispatchId": dispatch, "stopReason": reason})})
        return self.receive_from_orca(message_id)

    def test_un_worker_qui_a_fini_sans_worker_done_est_relance_sans_deranger_le_director(self):
        self.begin()
        step = self.stopped("msg_stop")
        self.assertEqual(step.next, "wait")
        send = self.world.ran("orca", "orchestration", "send")[-1]
        self.assertEqual(send[send.index("--to") + 1], "dispatch:ctx_1")
        self.assertIn("worker_done", send[send.index("--body") + 1])

    def test_un_worker_relance_qui_s_arrete_encore_sans_rapport_escalade(self):
        self.begin()
        self.stopped("msg_stop_1")
        step = self.stopped("msg_stop_2")
        self.assertEqual((step.next, step.reason), ("escalate", "Orca: Worker stopped without reporting: Worker term_1 exited"))

    def test_la_relance_est_rendue_au_worker_apres_son_prochain_message(self):
        self.begin()
        self.stopped("msg_stop_1")
        self.receive(message("dancer", "conductor", "report", "- Done."))
        self.assertEqual(self.stopped("msg_stop_2").next, "wait")

    def test_un_worker_tombe_en_erreur_escalade_sans_relance(self):
        self.begin()
        step = self.stopped("msg_stop", reason="errored")
        self.assertEqual(step.next, "escalate")
        self.assertFalse(self.world.ran("orca", "orchestration", "send"))

    def test_un_worker_inconnu_arrete_sans_rapport_escalade_avec_ce_qu_orca_en_dit(self):
        self.begin()
        self.orca_message("msg_stop", "escalation", "Worker term_1 exited", subject="Worker stopped without reporting")
        step = self.receive_from_orca("msg_stop")
        self.assertEqual(step.reason, "Orca: Worker stopped without reporting: Worker term_1 exited")

    def test_la_ligne_de_commande_lit_le_message_chez_orca(self):
        self.begin()
        self.orca_message("msg_1", "worker_done", message("dancer", "conductor", "report", "- Done."))
        code, lines = self.run_main("receive", "FEAT-001.2", "--message", "msg_1")
        self.assertEqual((code, lines[-1]), (0, "NEXT: wait"))

    # --- ligne de commande ---

    def test_la_derniere_ligne_dit_au_conductor_quoi_faire(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = ballet_rehearsal.main(["x", "begin", "3"], home=self.home, tools=self.tools)
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue().strip().splitlines()[-1], "NEXT: wait")

    def run_main(self, *arguments):
        output = io.StringIO()
        with redirect_stdout(output), mock.patch("sys.stderr", io.StringIO()):
            code = ballet_rehearsal.main(["x", *arguments], home=self.home, tools=self.tools)
        return code, output.getvalue().strip().splitlines()

    def test_une_escalade_est_un_cas_prevu_et_sort_avec_zero(self):
        self.begin()
        path = self.home / "incoming.md"
        path.write_text("not a message\n", encoding="utf-8")
        code, lines = self.run_main("receive", "FEAT-001.2", str(path))
        self.assertEqual(code, 0)
        self.assertTrue(lines[-1].startswith("NEXT: escalate invalid message"))

    def test_un_usage_invalide_sort_avec_deux_sans_rien_faire(self):
        self.assertEqual(self.run_main("begin")[0], 2)
        self.assertEqual(self.world.commands, [])

    # --- status ---

    def test_status_resume_la_rehearsal_et_redit_la_derniere_escalade(self):
        self.to_the_critic()
        self.receive(message("critic", "conductor", "verdict", "VERDICT: ESCALATE\n\n## Escalation\n\nSize."))
        code, lines = self.run_main("status", "FEAT-001.2")
        self.assertEqual(code, 0)
        self.assertIn("- pull request #8: ballet:escalated, Critic's last verdict APPROVED, CI green", lines)
        self.assertIn("- Dancer ↔ Critic round trips: 0 of 2", lines)
        self.assertEqual(lines[-1], "NEXT: escalate the Critic escalates: see its review")

    def test_status_sans_pr_dit_ce_qu_attend_la_rehearsal(self):
        self.begin()
        self.receive(message("dancer", "choreographer", "question", "1. A?"), question_id="msg_1")
        lines = self.run_main("status", "FEAT-001.2")[1]
        self.assertIn("- no pull request yet", lines)
        self.assertIn("- the dancer waits for the choreographer's answer (Orca message msg_1)", lines)
        self.assertEqual(lines[-1], "NEXT: wait")

    def test_status_json_rend_l_etat_brut(self):
        self.begin()
        code, lines = self.run_main("status", "FEAT-001.2", "--json")
        self.assertEqual(json.loads("\n".join(lines))["status"], "open")

    def test_la_reponse_du_director_rouvre_une_rehearsal_escaladee(self):
        self.begin()
        self.receive(message("dancer", "director", "question", "1. Touch the CI?"), question_id="msg_3")
        self.assertEqual(self.state()["status"], "escalated")
        self.receive(message("director", "dancer", "answer", "1. Yes."))
        self.assertEqual((self.state()["status"], self.state()["reason"]), ("open", ""))

    def test_le_dossier_d_etat_n_ecrit_plus_son_propre_gitignore(self):
        self.begin()
        self.assertFalse((self.home / ".ballet" / "run" / ".gitignore").exists())


if __name__ == "__main__":
    unittest.main()
