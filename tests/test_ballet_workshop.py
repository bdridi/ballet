import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_rehearsal  # noqa: E402
import ballet_workshop  # noqa: E402

PROFILE = """[project]
specs = "specs/"

[repos.antimurphy]
path = "."
proof = "pnpm proof"
"""

DRAFT = "# BUG-004 · Stock never goes negative\n\nSource: `@FEAT-001-C2`.\n\n## Context\n\nA gap.\n"


def message(kind, body, sender="dramaturg", to="conductor"):
    header = {"ballet": "message", "from": sender, "to": to, "type": kind, "subject": "BUG-004", "round": 1}
    return f"{json.dumps(header)}\n\n{body}\n"


def report(issue_type="Bug", draft=DRAFT):
    return message("report", f"- Type: {issue_type}\n\n## Decided alone\n\n- The negative stock is a bug, not a feature.\n\n## Issue draft\n\n{draft}")


class FakeWorld:
    """gh, git et orca, avec juste ce que le Conductor du Workshop lit ; chaque commande est notée."""

    def __init__(self, home):
        self.home = home
        self.commands = []
        self.dispatches = 0
        self.inbox = []
        self.branch = "workshop/BUG-004"
        self.new_commits = ["abc1234"]          # ce que le Dramaturg a commité
        self.changed = ["specs/backlog.md"]     # les fichiers de ses commits
        self.dirty = ""
        self.merge_failures = 0                 # `gh pr merge` échoue ces fois-ci
        self.issue_failures = 0                 # `gh issue create` échoue ces fois-ci
        self.statuses = []                      # le `Ballet status` écrit sur l'issue publiée, dans l'ordre

    def __call__(self, argv):
        self.commands.append(argv)
        tool, arguments = argv[0], argv[1:]
        if tool == "gh":
            return self.gh(arguments)
        if tool == "git":
            return self.git(arguments[2:])
        return self.orca(arguments)

    def gh(self, arguments):
        if arguments[:2] == ["pr", "create"]:
            return "https://github.com/o/r/pull/8\n"
        if arguments[:2] == ["pr", "view"]:
            return json.dumps({"headRefName": "workshop/BUG-004", "statusCheckRollup": []})
        if arguments[:2] == ["pr", "merge"]:
            if self.merge_failures:
                self.merge_failures -= 1
                raise ballet_rehearsal.RehearsalError("gh failed")
            return ""
        if arguments[:2] == ["issue", "create"]:
            if self.issue_failures:
                self.issue_failures -= 1
                raise ballet_rehearsal.RehearsalError("gh failed")
            return "https://github.com/o/r/issues/21\n"
        if arguments[:2] == ["api", "graphql"] and any("setIssueFieldValue" in argument for argument in arguments):
            option = next(argument for argument in arguments if argument.startswith("option="))
            self.statuses.append(option[len("option=OPT-"):])
            return "{}"
        if arguments[:2] == ["api", "graphql"]:
            options = [{"id": f"OPT-{name}", "name": name} for name in ("proposed", "ready", "in-rehearsal", "plan-review", "escalated", "done")]
            field = {"id": "FIELD", "name": "Ballet status", "options": options}
            return json.dumps({"data": {"repository": {"issue": {"id": "ISSUE"}}, "repositoryOwner": {"issueFields": {"nodes": [field]}}}})
        return ""

    def git(self, arguments):
        if arguments[0] == "worktree":
            return self.worktrees()
        if arguments[0] == "rev-parse" and arguments[1] == "--abbrev-ref":
            return self.branch + "\n"
        if arguments[0] == "rev-parse":
            return "c0ffee1\n"
        if arguments[0] == "rev-list" and arguments[1] == "--count":
            return "0\n"
        if arguments[0] == "rev-list":
            return "\n".join(self.new_commits)
        if arguments[0] == "status":
            return self.dirty
        if arguments[0] == "diff":
            return "\n".join(self.changed)
        return ""

    def worktrees(self):
        """Un worktree par branche de Workshop créée par Orca, plus le home."""
        listed = f"worktree {self.home}\nbranch refs/heads/main\n"
        for create in self.ran("orca", "worktree", "create"):
            branch = create[create.index("--branch") + 1]
            listed += f"\nworktree /wt/{branch.split('/', 1)[1]}\nbranch refs/heads/{branch}\n"
        return listed

    def orca(self, arguments):
        if arguments[:2] == ["orchestration", "inbox"]:
            return json.dumps({"ok": True, "result": {"messages": self.inbox}})
        if arguments[:2] == ["orchestration", "worker-start"]:
            self.dispatches += 1
            return json.dumps({"ok": True, "result": {"worker": {"dispatchId": f"ctx_{self.dispatches}"}}})
        return ""

    def ran(self, *prefix):
        return [command for command in self.commands if command[:len(prefix)] == list(prefix)]

    def sent_to_dramaturg(self):
        return [command[command.index("--body") + 1] for command in self.ran("orca", "orchestration", "send")]

    def said(self, kind, body, message_id="msg_1", sequence=1):
        self.inbox.append({"id": message_id, "type": kind, "body": body, "payload": {"dispatchId": "ctx_1"}, "sequence": sequence})
        return message_id


class BalletWorkshopTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        (self.home / ".ballet").mkdir()
        self.profile(PROFILE)
        environment = mock.patch.dict("os.environ", {"ORCA_CLI_COMMAND": "orca"})
        environment.start()
        self.addCleanup(environment.stop)
        self.world = FakeWorld(str(self.home))
        self.sleeps = []
        self.tools = ballet_rehearsal.Tools(run=self.world, sleep=self.sleeps.append)

    def profile(self, text):
        (self.home / ".ballet" / "config.toml").write_text(text, encoding="utf-8")

    def begin(self, item="BUG-004"):
        return ballet_workshop.begin(item, self.home, self.tools)

    def receive(self, kind, body, item="BUG-004"):
        message_id = self.world.said(kind, body, f"msg_{len(self.world.inbox) + 1}", len(self.world.inbox) + 1)
        return ballet_workshop.receive_from_orca(item, message_id, self.home, self.tools)

    def reports(self, text=None):
        return self.receive("worker_done", text or report())

    def resume(self, item="BUG-004"):
        return ballet_workshop.resume(item, self.home, self.tools)

    def state(self, item="BUG-004"):
        return json.loads((self.home / ".ballet" / "run" / f"workshop-{item}.json").read_text())

    def journal(self, event=None):
        lines = (self.home / ".ballet" / "run" / "journal.jsonl").read_text().splitlines()
        entries = [json.loads(line) for line in lines]
        return [entry for entry in entries if event in (None, entry["event"])]

    # --- begin ---

    def test_ouvre_un_worktree_sur_la_branche_du_workshop_depuis_main_et_lance_le_dramaturg(self):
        step = self.begin()
        self.assertEqual(step.next, "wait")
        self.assertTrue(self.world.ran("git", "-C", str(self.home.resolve()), "fetch", "origin", "main"))
        create = self.world.ran("orca", "worktree", "create")[0]
        self.assertEqual(create[create.index("--branch") + 1], "workshop/BUG-004")
        self.assertEqual(create[create.index("--base-branch") + 1], "origin/main")
        self.assertNotIn("--issue", create)
        start = self.world.ran("orca", "orchestration", "worker-start")[0]
        self.assertEqual(start[start.index("--worktree") + 1], "path:/wt/BUG-004")
        self.assertEqual(start[start.index("--task-title") + 1], "Dramaturg · BUG-004")
        self.assertEqual(self.state()["dispatch"], "ctx_1")

    def test_la_spec_du_worker_nomme_son_skill_son_rapport_et_ce_qu_il_ne_fait_pas(self):
        self.begin()
        spec_file = self.world.ran("orca", "orchestration", "worker-start")[0]
        spec = Path(spec_file[spec_file.index("--spec-file") + 1]).read_text()
        for expected in ("/ballet:dramaturg", "In an autopilot Workshop", "BUG-004", "- Type:", "## Decided alone", "## Issue draft",
                         "- Blocked:", "never ask", "worker_done", "Never push"):
            self.assertIn(expected, spec)

    def test_l_etat_est_a_part_des_sessions_et_des_rehearsals(self):
        self.begin()
        run = self.home / ".ballet" / "run"
        self.assertEqual(sorted(path.name for path in run.glob("*.json")), ["workshop-BUG-004.json"])
        self.assertNotIn("id", self.state())
        self.assertEqual([entry for entry in self.journal() if "rehearsal" in entry], [])
        self.assertEqual({entry["workshop"] for entry in self.journal()}, {"BUG-004"})

    def test_le_journal_garde_le_lancement_du_dramaturg_avec_sa_mission(self):
        self.begin()
        self.assertEqual([entry["event"] for entry in self.journal()][:3], ["begin", "handoff", "wait"])
        start = self.journal("handoff")[0]["detail"]
        self.assertEqual((start["role"], start["how"], start["dispatch"], start["agent"]), ("dramaturg", "start", "ctx_1", "claude"))
        self.assertIn("Frame BUG-004", start["text"])

    def test_refuse_d_ouvrir_deux_fois_le_meme_element_mais_pas_deux_elements(self):
        self.begin()
        with self.assertRaisesRegex(ballet_workshop.WorkshopError, "already open"):
            self.begin()
        self.assertEqual(self.begin("FEAT-007").next, "wait")

    def test_refuse_de_demarrer_sans_profil_valide(self):
        self.profile("[project]\n")
        with self.assertRaisesRegex(ballet_workshop.WorkshopError, "init-project"):
            self.begin()

    def test_un_dramaturg_qui_ne_peut_pas_demarrer_escalade_et_la_reprise_le_relance(self):
        self.profile(PROFILE + '\n[roles.dramaturg]\ncli = "gemini-cli"\n')
        step = self.begin()
        self.assertEqual(step.next, "escalate")
        self.assertIn("cannot run as an Orca worker", step.reason)
        self.assertEqual(self.state()["status"], "escalated")
        self.profile(PROFILE)
        self.assertEqual(self.resume().next, "wait")
        self.assertEqual(self.state()["dispatch"], "ctx_1")

    # --- le rapport du Dramaturg : les specs, puis l'issue ---

    def test_les_specs_vont_sur_main_par_une_pr_puis_l_issue_est_publiee_proposee(self):
        self.begin()
        step = self.reports()
        self.assertEqual(step.next, "done")
        self.assertIn("issue #21", step.reason)
        commands = self.world.commands
        self.assertEqual(self.world.ran("git", "-C", str(self.home.resolve()), "push", "--set-upstream", "origin", "workshop/BUG-004")[0][-1], "workshop/BUG-004")
        create = self.world.ran("gh", "pr", "create")[0]
        self.assertEqual(create[create.index("--head") + 1], "workshop/BUG-004")
        self.assertNotIn("Closes", create[create.index("--body") + 1])
        merge, issue = commands.index(["gh", "pr", "merge", "8", "--rebase"]), commands.index(self.world.ran("gh", "issue", "create")[0])
        self.assertLess(merge, issue)
        self.assertEqual(self.world.ran("gh", "issue", "create")[0][-2:], ["--type", "Bug"])
        self.assertEqual(self.world.statuses, ["proposed"])
        self.assertTrue(self.world.ran("orca", "worktree", "rm"))
        self.assertEqual((self.state()["status"], self.state()["issue"], self.state()["ballet_status"]), ("done", "21", "proposed"))

    def test_l_issue_publiee_est_le_brouillon_du_rapport_sans_son_en_tete(self):
        self.begin()
        self.reports()
        issue = self.world.ran("gh", "issue", "create")[0]
        self.assertEqual(issue[issue.index("--title") + 1], "BUG-004 · Stock never goes negative")
        self.assertIn("A gap.", issue[issue.index("--body") + 1])
        self.assertNotIn("Decided alone", issue[issue.index("--body") + 1])

    def test_un_type_dispense_de_l_acceptation_sort_pret_d_emblee(self):
        self.profile(PROFILE + '\n[workshop]\nqueue_approval_skipped = ["Bug"]\n')
        self.begin()
        self.reports()
        self.assertEqual(self.world.statuses, ["ready"])
        self.assertEqual(self.state()["ballet_status"], "ready")

    def test_un_autre_type_reste_propose_quand_le_director_n_en_a_dispense_qu_un(self):
        self.profile(PROFILE + '\n[workshop]\nqueue_approval_skipped = ["Task"]\n')
        self.begin()
        self.reports()
        self.assertEqual(self.world.statuses, ["proposed"])

    def test_le_type_du_rapport_donne_le_type_de_l_issue(self):
        self.begin()
        self.reports(report("Feature", "# FEAT-007 · Sign in\n\n## Context\n\nWhy.\n"))
        self.assertEqual(self.world.ran("gh", "issue", "create")[0][-2:], ["--type", "Feature"])

    def test_sans_specs_ecrites_ni_push_ni_pr_et_l_issue_est_publiee(self):
        self.world.new_commits, self.world.changed = [], []
        self.begin()
        step = self.reports()
        self.assertEqual(step.next, "done")
        self.assertFalse(self.world.ran("gh", "pr"))
        self.assertFalse([command for command in self.world.commands if "push" in command])
        self.assertTrue(self.world.ran("gh", "issue", "create"))
        self.assertIn("no specs written", "\n".join(step.render().splitlines()))

    def test_la_decision_prise_seul_reste_dans_le_journal_avec_le_rapport_entier(self):
        self.begin()
        self.reports()
        self.assertIn("The negative stock is a bug", self.journal("message")[0]["detail"]["text"])

    # --- la politique ---

    def test_un_dramaturg_qui_touche_au_code_est_renvoye_une_fois_et_rien_n_est_pousse(self):
        self.world.changed = ["specs/backlog.md", "src/main.rs"]
        self.begin()
        step = self.reports()
        self.assertEqual(step.next, "wait")
        self.assertIn("src/main.rs", self.world.sent_to_dramaturg()[0])
        self.assertFalse([command for command in self.world.commands if "push" in command])
        self.assertEqual(self.state()["report"], "")

    def test_une_deuxieme_violation_escalade_sans_rien_pousser(self):
        self.world.changed = ["src/main.rs"]
        self.begin()
        self.reports()
        step = self.reports()
        self.assertEqual(step.next, "escalate")
        self.assertIn("policy: the dramaturg broke the rules", step.reason)
        self.assertFalse(self.world.ran("gh", "pr"))
        self.assertFalse(self.world.ran("gh", "issue"))

    def test_un_arbre_sale_est_une_violation(self):
        self.world.dirty = " M specs/backlog.md\n"
        self.begin()
        self.assertEqual(self.reports().next, "wait")
        self.assertIn("uncommitted changes", self.world.sent_to_dramaturg()[0])

    def test_la_correction_du_dramaturg_suffit_une_fois_l_arbre_en_regle(self):
        self.world.changed = ["src/main.rs"]
        self.begin()
        self.reports()
        self.world.changed = ["specs/backlog.md"]
        self.assertEqual(self.reports().next, "done")

    # --- un rapport qui ne dit pas tout, un Dramaturg bloqué ---

    def test_un_dramaturg_bloque_escalade_avec_son_motif_sans_rien_publier(self):
        self.begin()
        step = self.reports(message("report", "- Blocked: BUG-004 is not in the backlog."))
        self.assertEqual(step.next, "escalate")
        self.assertEqual(step.reason, "the dramaturg is blocked: BUG-004 is not in the backlog.")
        self.assertFalse(self.world.ran("gh"))

    def test_un_rapport_sans_type_valide_est_renvoye_une_fois_puis_escalade(self):
        self.begin()
        bad = report("Epic")
        self.assertEqual(self.reports(bad).next, "wait")
        self.assertIn("Epic", self.world.sent_to_dramaturg()[0])
        step = self.reports(bad)
        self.assertEqual(step.next, "escalate")
        self.assertIn("expected Feature, Bug, Task", step.reason)
        self.assertFalse(self.world.ran("gh"))

    def test_un_rapport_sans_brouillon_est_renvoye_au_dramaturg(self):
        self.begin()
        step = self.reports(message("report", "- Type: Bug\n\n## Decided alone\n\n- None."))
        self.assertEqual(step.next, "wait")
        self.assertIn("no `## Issue draft` section", self.world.sent_to_dramaturg()[0])

    def test_une_question_du_dramaturg_escalade_car_personne_n_y_repond(self):
        self.begin()
        message_id = self.world.said("question", message("question", "1. Which name?", to="choreographer"))
        step = ballet_workshop.receive_from_orca("BUG-004", message_id, self.home, self.tools)
        self.assertEqual(step.next, "escalate")
        self.assertIn("nobody answers", step.reason)

    def test_un_message_d_un_autre_role_est_refuse(self):
        self.begin()
        step = self.receive("worker_done", message("report", "- Type: Bug", sender="dancer"))
        self.assertEqual(step.next, "escalate")
        self.assertIn("only the dramaturg plays", step.reason)

    def test_un_message_qui_n_est_pas_au_format_ballet_est_refuse(self):
        self.begin()
        step = self.receive("worker_done", "hello")
        self.assertEqual(step.next, "escalate")
        self.assertIn("invalid message", step.reason)

    # --- le worker qui s'arrête sans rapport ---

    def stopped(self):
        message_id = "msg_stop"
        self.world.inbox.append({"id": message_id, "type": "escalation", "subject": "worker stopped", "body": "done",
                                 "payload": {"dispatchId": "ctx_1", "stopReason": "finished"}, "sequence": 9})
        return ballet_workshop.receive_from_orca("BUG-004", message_id, self.home, self.tools)

    def test_un_dramaturg_qui_s_arrete_sans_rapport_est_relance_une_fois(self):
        self.begin()
        self.assertEqual(self.stopped().next, "wait")
        self.assertIn("worker_done", self.world.sent_to_dramaturg()[0])
        step = self.stopped()
        self.assertEqual(step.next, "escalate")
        self.assertIn("Orca: worker stopped", step.reason)

    def test_un_message_du_dramaturg_remet_ses_relances_a_zero(self):
        self.begin()
        self.stopped()
        self.assertEqual(self.state()["nudges"], 1)
        self.reports()
        self.assertEqual(self.state()["nudges"], 0)

    def test_on_retrouve_le_dernier_message_d_un_dispatch(self):
        self.begin()
        self.world.said("worker_done", report(), "msg_old", 1)
        self.world.inbox[0]["payload"] = {"dispatchId": "ctx_other"}
        self.world.said("worker_done", report(), "msg_new", 2)
        step = ballet_workshop.receive_from_orca("BUG-004", "ctx_1", self.home, self.tools, by="dispatch")
        self.assertEqual(step.next, "done")

    # --- le merge, la publication et la reprise ---

    def test_les_specs_sont_mergees_sans_lire_ni_attendre_la_ci(self):
        self.begin()
        step = self.reports()
        self.assertEqual(step.next, "done")
        self.assertEqual(self.sleeps, [])

    def test_un_merge_qui_echoue_se_reprend_sans_repousser_ni_rouvrir_la_pr(self):
        self.world.merge_failures = 1
        self.begin()
        step = self.reports()
        self.assertEqual(step.next, "escalate")
        self.assertEqual(step.reason, "gh failed")
        self.assertFalse(self.state()["merged"])
        self.assertEqual(self.state()["pull_request"], "8")
        self.assertFalse(self.world.ran("gh", "issue", "create"))
        self.assertEqual(self.resume().next, "done")
        self.assertEqual(len(self.world.ran("gh", "pr", "create")), 1)
        self.assertEqual(len([command for command in self.world.commands if "push" in command and "--set-upstream" in command]), 1)

    def test_une_publication_qui_echoue_apres_le_merge_se_reprend_sans_remerger(self):
        self.world.issue_failures = 1
        self.begin()
        step = self.reports()
        self.assertEqual(step.next, "escalate")
        self.assertTrue(self.state()["merged"])
        self.assertEqual(self.resume().next, "done")
        self.assertEqual(len(self.world.ran("gh", "pr", "merge")), 1)
        self.assertEqual(self.world.statuses, ["proposed"])

    def test_reprendre_sans_rapport_n_a_rien_a_reprendre(self):
        self.begin()
        step = self.resume()
        self.assertEqual(step.next, "wait")
        self.assertIn("nothing to resume", step.render())

    def test_une_session_finie_ne_recoit_ni_ne_reprend_plus_rien(self):
        self.begin()
        self.reports()
        commands_before = len(self.world.commands)
        self.assertEqual(self.resume().next, "done")
        self.assertEqual(self.receive("worker_done", report()).next, "done")
        self.assertEqual(len(self.world.commands), commands_before)    # rien n'est relu chez Orca, rien n'est refait
        self.assertEqual(self.state()["issue"], "21")

    # --- status et ligne de commande ---

    def test_le_statut_dit_ou_en_est_la_session(self):
        self.begin()
        self.assertEqual(ballet_workshop.status("BUG-004", self.home, self.tools).next, "wait")
        self.reports()
        lines = ballet_workshop.status("BUG-004", self.home, self.tools).render()
        self.assertIn("Workshop BUG-004: done", lines)
        self.assertIn("specs: pull request #8, merged", lines)
        self.assertIn("issue #21, Ballet status proposed", lines)
        self.assertIn("NEXT: done", lines)

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ballet_workshop.main(["ballet_workshop.py", *argv], home=self.home, tools=self.tools)
        return code, out.getvalue(), err.getvalue()

    def test_la_ligne_de_commande_ouvre_la_session_et_l_affiche(self):
        code, out, _ = self.run_main("begin", "BUG-004")
        self.assertEqual(code, 0)
        self.assertTrue(out.endswith("NEXT: wait\n"))

    def test_un_element_qui_n_est_pas_une_ligne_du_backlog_est_un_mauvais_usage(self):
        for argument in ("#12", "CAP-001", "bug-4", "BUG-"):
            with self.subTest(argument=argument):
                code, _, err = self.run_main("begin", argument)
                self.assertEqual(code, 2)
                self.assertIn("not an item", err)

    def test_sans_element_la_seule_session_ouverte_est_prise(self):
        self.begin()
        self.world.said("worker_done", report(), "msg_1")
        code, out, _ = self.run_main("receive", "--message", "msg_1")
        self.assertEqual(code, 0)
        self.assertIn("NEXT: done", out)

    def test_sans_element_et_plusieurs_sessions_ouvertes_il_faut_nommer_l_element(self):
        self.begin()
        self.begin("FEAT-007")
        code, _, err = self.run_main("status")
        self.assertEqual(code, 2)
        self.assertIn("2 Workshops are open (BUG-004, FEAT-007)", err)

    def test_une_session_inconnue_s_affiche_en_escalade(self):
        code, out, _ = self.run_main("status", "BUG-009")
        self.assertEqual(code, 0)
        self.assertIn("NEXT: escalate no Workshop of BUG-009", out)

    def test_deux_sessions_tournent_cote_a_cote_sans_se_marcher_dessus(self):
        self.begin()
        self.begin("FEAT-007")
        self.assertEqual(self.state("FEAT-007")["dispatch"], "ctx_2")
        self.assertEqual(self.state()["dispatch"], "ctx_1")


if __name__ == "__main__":
    unittest.main()
