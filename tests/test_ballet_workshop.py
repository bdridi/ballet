import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_maestro  # noqa: E402
import ballet_runtime  # noqa: E402
import ballet_rehearsal  # noqa: E402
import ballet_store  # noqa: E402
import ballet_workshop  # noqa: E402

PROFILE = """[project]
specs = "specs/"

[repos.antimurphy]
path = "."
proof = "pnpm proof"
"""

DRAFT = "# BUG-004 · Stock never goes negative\n\nSource: `@FEAT-001-C2`.\n\n## Context\n\nA gap.\n"


def message(kind, body, sender="dramaturg", to="conductor", round=1):
    header = {"ballet": "message", "from": sender, "to": to, "type": kind, "subject": "BUG-004", "round": round}
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
        self.run_batch = []                     # les messages en attente du Run du Conductor, consommés par `check --run`
        self.branch = "workshop/BUG-004"
        self.new_commits = ["abc1234"]          # ce que le Dramaturg a commité
        self.changed = ["specs/backlog.md"]     # les fichiers de ses commits
        self.dirty = ""
        self.merge_failures = 0                 # `gh pr merge` échoue ces fois-ci
        self.issue_failures = 0                 # `gh issue create` échoue ces fois-ci
        self.statuses = []                      # le `Ballet status` écrit sur l'issue publiée, dans l'ordre
        self.label_failures = 0                 # `gh issue edit` (le libellé) échoue ces fois-ci
        self.comment_failures = 0               # `gh issue comment` échoue ces fois-ci…
        self.comment_after = 0                  # …après ce nombre de commentaires réussis
        self.issues = []                        # les issues déjà dans le repo, comme `gh issue list` les rend
        self.links = []                         # les liens « blocked by » posés : (issue bloquée, bloqueur)

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
        if arguments[:2] == ["issue", "list"]:
            return json.dumps(self.issues)
        if arguments[:2] == ["api", "graphql"] and any("blocker: issue" in argument for argument in arguments):
            number = {name: next(argument for argument in arguments if argument.startswith(f"{name}=")).split("=")[1] for name in ("issue", "blocker")}
            return json.dumps({"data": {"repository": {name: {"id": f"ID-{found}", "blockedBy": {"nodes": []}} for name, found in number.items()}}})
        if arguments[:2] == ["api", "graphql"] and any("addBlockedBy" in argument for argument in arguments):
            self.links.append(tuple(next(argument for argument in arguments if argument.startswith(f"{name}=ID-")).split("=ID-")[1]
                                    for name in ("issue", "blocker")))
            return "{}"
        if arguments[:2] == ["issue", "comment"]:
            if self.comment_failures and self.comment_after == 0:
                self.comment_failures -= 1
                raise ballet_rehearsal.RehearsalError("gh failed")
            self.comment_after -= 1
            return ""
        if arguments[:2] == ["issue", "edit"] and self.label_failures:
            self.label_failures -= 1
            raise ballet_rehearsal.RehearsalError("gh failed")
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
        if arguments[:2] == ["orchestration", "check"]:
            batch, self.run_batch = self.run_batch, []
            return json.dumps({"ok": True, "result": {"messages": batch}})
        if arguments[:2] == ["orchestration", "worker-start"]:
            self.dispatches += 1
            return json.dumps({"ok": True, "result": {"worker": {"dispatchId": f"ctx_{self.dispatches}"}}})
        return ""

    def ran(self, *prefix):
        return [command for command in self.commands if command[:len(prefix)] == list(prefix)]

    def sent_to_dramaturg(self):
        return [command[command.index("--body") + 1] for command in self.ran("orca", "orchestration", "send")]

    def said(self, kind, body, message_id="msg_1", sequence=1, dispatch="ctx_1"):
        self.inbox.append({"id": message_id, "type": kind, "body": body, "payload": {"dispatchId": dispatch}, "sequence": sequence})
        return message_id


class BalletWorkshopTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        (self.home / ".ballet").mkdir()
        self.profile(PROFILE)
        environment = mock.patch.dict("os.environ", {"ORCA_CLI_COMMAND": "orca", "BALLET_HOME": str(self.home / "ballet-home")})
        environment.start()
        self.addCleanup(environment.stop)
        self.world = FakeWorld(str(self.home))
        self.sleeps = []
        self.tools = ballet_rehearsal.Tools(run=self.world, sleep=self.sleeps.append)

    def profile(self, text):
        (self.home / ".ballet" / "config.toml").write_text(text, encoding="utf-8")

    def begin(self, item="BUG-004"):
        return ballet_workshop.begin(item, self.home, self.tools)

    def receive(self, kind, body, item="BUG-004", dispatch="ctx_1"):
        message_id = self.world.said(kind, body, f"msg_{len(self.world.inbox) + 1}", len(self.world.inbox) + 1, dispatch)
        return ballet_workshop.receive_from_orca(item, message_id, self.home, self.tools)

    def reports(self, text=None):
        return self.receive("worker_done", text or report())

    def resume(self, item="BUG-004"):
        return ballet_workshop.resume(item, self.home, self.tools)

    def state(self, item="BUG-004"):
        return ballet_store.load(self.home, "workshop", item)

    def journal(self, event=None):
        entries = ballet_store.journal(self.home, "workshop")
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
        self.assertEqual([state["item"] for state in ballet_store.all_of(self.home, "workshop")], ["BUG-004"])
        self.assertEqual((ballet_store.all_of(self.home, "session"), ballet_store.all_of(self.home, "rehearsal")), ([], []))
        self.assertNotIn("id", self.state())
        self.assertEqual(ballet_store.journal(self.home, "rehearsal"), [])
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
        self.assertNotIn("Issue draft", issue[issue.index("--body") + 1])

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

    def test_un_type_feature_dispense_de_l_acceptation_sort_pret_d_emblee(self):
        self.profile(PROFILE + '\n[workshop]\nqueue_approval_skipped = ["Feature"]\n')
        self.begin()
        self.reports(report("Feature", "# FEAT-007 · Sign in\n\n## Context\n\nWhy.\n"))
        self.assertEqual(self.world.statuses, ["ready"])
        self.assertEqual(self.state()["ballet_status"], "ready")

    def test_la_ligne_depends_on_du_brouillon_pose_le_lien_blocked_by_et_le_dit(self):
        self.world.issues = [{"number": 7, "title": "FEAT-002 · Cart", "body": "", "state": "OPEN"}]
        self.begin()
        step = self.reports(report("Feature", "# FEAT-007 · Sign in\n\n- **Depends on**: FEAT-002\n\n## Context\n\nWhy.\n"))
        self.assertEqual(step.next, "done")
        self.assertEqual(self.world.links, [("21", "7")])
        self.assertIn("#21 is now blocked by #7 (FEAT-002)", step.render())

    def test_une_dependance_inconnue_arrete_le_workshop_avant_de_creer_l_issue(self):
        self.begin()
        step = self.reports(report("Feature", "# FEAT-007 · Sign in\n\n- **Depends on**: FEAT-099\n\n## Context\n\nWhy.\n"))
        self.assertEqual(step.next, "escalate")
        self.assertIn("unknown dependency FEAT-099", step.render())
        self.assertFalse(self.world.ran("gh", "issue", "create"))

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

    # --- ce que le Dramaturg décide seul ---

    def body_of_issue(self):
        issue = self.world.ran("gh", "issue", "create")[0]
        return issue[issue.index("--body") + 1]

    def test_les_decisions_prises_seul_sont_dans_l_issue_avant_son_plan(self):
        self.begin()
        self.reports()
        body = self.body_of_issue()
        self.assertIn("## Decided alone\n\n- The negative stock is a bug, not a feature.", body)
        self.assertLess(body.index("## Decided alone"), body.index("## Plan"))

    def test_l_issue_ou_le_dramaturg_a_decide_seul_porte_le_libelle_decided_alone(self):
        self.begin()
        step = self.reports()
        label = self.world.ran("gh", "label", "create", "ballet:decided-alone")
        self.assertEqual(len(label), 1)
        self.assertEqual(self.world.ran("gh", "issue", "edit", "21", "--add-label", "ballet:decided-alone")[0][-1], "ballet:decided-alone")
        self.assertTrue(self.state()["marked"])
        self.assertIn("marked ballet:decided-alone (1 decision(s))", step.render())

    def test_sans_decision_prise_seul_l_issue_n_a_ni_section_ni_libelle(self):
        self.begin()
        self.reports(message("report", f"- Type: Bug\n\n## Issue draft\n\n{DRAFT}"))
        self.assertNotIn("Decided alone", self.body_of_issue())
        self.assertFalse(self.world.ran("gh", "label"))
        self.assertFalse(self.world.ran("gh", "issue", "edit"))

    def test_un_libelle_qui_echoue_se_reprend_sans_republier_l_issue(self):
        self.world.label_failures = 1
        self.begin()
        step = self.reports()
        self.assertEqual(step.next, "escalate")
        self.assertEqual(self.state()["issue"], "21")
        self.assertEqual(self.resume().next, "done")
        self.assertEqual(len(self.world.ran("gh", "issue", "create")), 1)
        self.assertTrue(self.state()["marked"])
        self.assertEqual(self.world.statuses, ["proposed"])

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
        message_id = self.world.said("question", message("question", "1. Which name?", to="director"))
        step = ballet_workshop.receive_from_orca("BUG-004", message_id, self.home, self.tools)
        self.assertEqual(step.next, "escalate")
        self.assertIn("nobody answers", step.reason)

    def test_un_message_d_un_autre_role_est_refuse(self):
        self.begin()
        step = self.receive("worker_done", message("report", "- Type: Bug", sender="dancer"))
        self.assertEqual(step.next, "escalate")
        self.assertIn("only the dramaturg and the choreographer it consults play", step.reason)

    def test_un_message_qui_n_est_pas_au_format_ballet_est_refuse(self):
        self.begin()
        step = self.receive("worker_done", "hello")
        self.assertEqual(step.next, "escalate")
        self.assertIn("invalid message", step.reason)

    # --- nudge : le Monitor a vu le Workshop sans nouvelles ---

    def nudge(self, item="BUG-004"):
        return ballet_workshop.nudge(item, self.home, self.tools)

    def reminders(self):
        """Les rappels envoyés : (dispatch visé, sujet, corps)."""
        sends = [command for command in self.world.ran("orca", "orchestration", "send")
                 if "Ballet is waiting for you" in command[command.index("--subject") + 1]]
        return [(command[command.index("--to") + 1], command[command.index("--subject") + 1], command[command.index("--body") + 1])
                for command in sends]

    def test_nudge_rappelle_au_dramaturg_son_message_et_le_journalise_en_relance(self):
        self.begin()
        step = self.nudge()
        self.assertEqual((step.next, step.done), ("wait", ["the dramaturg reminded: Ballet was waiting for it"]))
        self.assertEqual(self.reminders(), [("dispatch:ctx_1", "BUG-004 · dramaturg: Ballet is waiting for you", ballet_rehearsal.IDLE_REMINDER)])
        relance = self.journal("handoff")[-1]["detail"]
        self.assertEqual((relance["role"], relance["how"], relance["text"]), ("dramaturg", "nudge", ballet_rehearsal.IDLE_REMINDER))

    def test_nudge_vise_le_choreographer_tant_que_sa_reponse_est_attendue(self):
        self.begin()
        self.asks()
        self.nudge()
        self.assertEqual([found[0] for found in self.reminders()], ["dispatch:ctx_2"])
        self.assertIn("choreographer", self.reminders()[0][1])

    def test_nudge_revient_au_dramaturg_une_fois_la_question_repondue(self):
        self.begin()
        self.asks()
        self.advises()
        self.nudge()
        self.assertEqual([found[0] for found in self.reminders()], ["dispatch:ctx_1"])

    def test_nudge_n_est_pas_de_l_activite_pour_le_journal_du_pas_wait(self):
        self.begin()
        before = [entry["event"] for entry in self.journal()]
        self.nudge()
        self.assertEqual([entry["event"] for entry in self.journal()], before + ["handoff"])

    def test_nudge_d_un_workshop_escalade_redit_son_etat_sans_rien_envoyer(self):
        self.begin()
        self.receive("worker_done", message("question", "1. Which name?", to="director"))
        step = self.nudge()
        self.assertEqual(step.next, "escalate")
        self.assertIn("is escalated", step.done[0])
        self.assertEqual(self.reminders(), [])

    def test_la_ligne_de_commande_nudge_sans_element_vise_le_seul_workshop_ouvert(self):
        self.begin()
        code, out, _ = self.run_main("nudge")
        self.assertEqual(code, 0)
        self.assertTrue(out.strip().endswith("NEXT: wait"))
        self.assertEqual(len(self.reminders()), 1)
        self.assertEqual(self.run_main("nudge", "BUG-004")[0], 0)
        self.assertEqual(self.run_main("nudge", "BUG-004", "--bogus")[0], 2)

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

    def test_la_fin_du_workshop_donne_ses_frictions_et_les_garde(self):
        self.begin()
        step = self.reports()
        self.assertEqual(step.next, "done")
        self.assertTrue(step.done[-1].startswith("frictions of Workshop BUG-004 ("))
        self.assertTrue(step.done[-1].endswith("): none"))
        self.assertEqual(self.journal("frictions")[0]["detail"], self.state()["frictions"])

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

    # --- l'avis du Choreographer ---

    QUESTION = "1. Is it one Dancer session? Recommendation: yes."
    ANSWER = "1. One session. Recommendation: keep it as one."

    def asks(self, text=None, round=1):
        return self.receive("worker_done", message("question", text or self.QUESTION, to="choreographer", round=round))

    def advises(self, text=None, to="dramaturg", kind="answer"):
        return self.receive("worker_done", message(kind, text or self.ANSWER, sender="choreographer", to=to), dispatch="ctx_2")

    def test_une_question_au_choreographer_lance_son_worker_dans_le_worktree_du_workshop(self):
        self.begin()
        step = self.asks()
        self.assertEqual(step.next, "wait")
        start = self.world.ran("orca", "orchestration", "worker-start")[1]
        self.assertEqual(start[start.index("--worktree") + 1], "path:/wt/BUG-004")
        self.assertEqual(start[start.index("--task-title") + 1], "Choreographer · BUG-004")
        spec = Path(start[start.index("--spec-file") + 1]).read_text()
        for expected in ("/ballet:choreographer", "When consulted during a Workshop", self.QUESTION, "Write nothing", "type: answer"):
            self.assertIn(expected, spec)
        state = self.state()
        self.assertEqual((state["advisor_dispatch"], state["rounds"]), ("ctx_2", 1))
        self.assertIn(self.QUESTION, state["question"])

    def test_la_reponse_du_choreographer_va_au_dramaturg_qui_reprend_son_cadrage(self):
        self.begin()
        self.asks()
        step = self.advises()
        self.assertEqual(step.next, "wait")
        self.assertEqual(len(self.world.sent_to_dramaturg()), 1)
        self.assertIn(self.ANSWER, self.world.sent_to_dramaturg()[0])
        send = self.world.ran("orca", "orchestration", "send")[0]
        self.assertEqual(send[send.index("--to") + 1], "dispatch:ctx_1")
        self.assertIn(self.ANSWER, self.state()["advice"])
        self.assertEqual(self.state()["question"], "")
        self.assertEqual(self.reports().next, "done")

    def consult(self, rounds):
        """`rounds` tours complets : une question du Dramaturg, une réponse du Choreographer."""
        for round in range(1, rounds + 1):
            self.asks(round=round)
            self.advises()

    def test_une_nouvelle_question_va_au_choreographer_deja_lance_dans_sa_session(self):
        self.begin()
        self.consult(1)
        step = self.asks("1. And the migration? Recommendation: none.", round=2)
        self.assertEqual(step.next, "wait")
        self.assertEqual(len(self.world.ran("orca", "orchestration", "worker-start")), 2)
        send = self.world.ran("orca", "orchestration", "send")[-1]
        self.assertEqual(send[send.index("--to") + 1], "dispatch:ctx_2")
        self.assertIn("And the migration?", send[send.index("--body") + 1])
        self.assertEqual(self.state()["rounds"], 2)
        self.assertEqual(self.advises().next, "wait")
        self.assertEqual(self.reports().next, "done")

    def test_les_tours_sont_bornes_par_max_exchange_rounds_du_plugin(self):
        self.begin()
        self.consult(3)
        step = self.asks(round=4)
        self.assertEqual(step.next, "escalate")
        self.assertIn("over max_exchange_rounds (3)", step.reason)
        self.assertEqual(len(self.world.ran("orca", "orchestration", "send")), 5)    # 3 réponses, les questions 2 et 3, pas la 4e

    def test_le_profil_du_projet_l_emporte_sur_la_borne_du_plugin(self):
        self.profile(PROFILE + "\n[escalation]\nmax_exchange_rounds = 5\n")
        self.begin()
        self.consult(5)
        self.assertIn("over max_exchange_rounds (5)", self.asks(round=6).reason)
        self.profile(PROFILE + "\n[escalation]\nmax_exchange_rounds = 1\n")
        self.begin("FEAT-007")
        message_id = self.world.said("worker_done", message("question", self.QUESTION, to="choreographer"), "msg_f1", 99, "ctx_8")
        self.assertEqual(ballet_workshop.receive_from_orca("FEAT-007", message_id, self.home, self.tools).next, "wait")

    def test_le_script_compte_les_tours_sans_se_fier_a_l_en_tete(self):
        self.profile(PROFILE + "\n[escalation]\nmax_exchange_rounds = 1\n")
        self.begin()
        self.consult(1)
        step = self.asks(round=1)
        self.assertEqual(step.next, "escalate")
        self.assertIn("round 2", step.reason)

    def test_la_mission_du_dramaturg_dit_la_borne_des_tours(self):
        self.profile(PROFILE + "\n[escalation]\nmax_exchange_rounds = 2\n")
        self.begin()
        start = self.world.ran("orca", "orchestration", "worker-start")[0]
        self.assertIn("up to 2 round(s)", Path(start[start.index("--spec-file") + 1]).read_text())

    def comments(self):
        return [command for command in self.world.ran("gh", "issue", "comment")]

    def test_les_echanges_sont_publies_sur_l_issue_dans_l_ordre_une_fois_creee(self):
        self.begin()
        self.consult(2)
        self.assertEqual(self.comments(), [])
        step = self.reports()
        comments = self.comments()
        self.assertEqual([comment[3] for comment in comments], ["21"] * 4)
        bodies = [comment[comment.index("--body") + 1] for comment in comments]
        self.assertIn(self.QUESTION, bodies[0])
        self.assertIn(self.ANSWER, bodies[1])
        self.assertLess(self.world.commands.index(self.world.ran("gh", "issue", "create")[0]), self.world.commands.index(comments[0]))
        self.assertIn("4 exchange(s) with the choreographer published on #21", step.render())

    def test_une_publication_d_echange_qui_echoue_se_reprend_sans_doublon(self):
        self.begin()
        self.consult(1)
        self.world.comment_failures = 1
        self.world.comment_after = 1
        self.assertEqual(self.reports().next, "escalate")
        self.assertEqual(self.state()["exchanges_published"], 1)
        self.assertEqual(self.resume().next, "done")
        self.assertEqual(len(self.comments()), 3)    # le premier, l'échec, puis le second seulement
        self.assertEqual(self.state()["exchanges_published"], 2)

    def test_sans_consultation_aucun_commentaire(self):
        self.begin()
        self.reports()
        self.assertEqual(self.comments(), [])

    def test_la_publication_lie_l_element_a_son_issue_dans_le_journal_sans_le_renommer(self):
        self.begin()
        self.consult(1)
        self.reports()
        published = self.journal("published")
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["workshop"], "BUG-004")
        self.assertEqual(published[0]["detail"], {"item": "BUG-004", "issue": "21", "type": "Bug", "status": "proposed",
                                                  "picked": False, "decided_alone": 1, "exchanges": 2})
        self.assertEqual({entry["workshop"] for entry in self.journal()}, {"BUG-004"})

    def test_une_publication_reprise_ne_lie_qu_une_fois(self):
        self.world.label_failures = 1
        self.begin()
        self.reports()
        self.resume()
        self.assertEqual(len(self.journal("published")), 1)

    def test_chaque_echange_est_au_journal(self):
        self.begin()
        self.consult(1)
        messages = [entry["detail"] for entry in self.journal("message")]
        self.assertEqual([(m["from"], m["type"]) for m in messages], [("dramaturg", "question"), ("choreographer", "answer")])
        handoffs = [(entry["detail"]["role"], entry["detail"]["how"]) for entry in self.journal("handoff")]
        self.assertEqual(handoffs, [("dramaturg", "start"), ("choreographer", "start"), ("dramaturg", "send")])

    def test_le_choreographer_est_juge_depuis_la_derniere_question(self):
        self.begin()
        self.consult(1)
        self.world.dirty = " M specs/features/FEAT-007.md\n"
        self.asks(round=2)
        step = self.advises()
        self.assertEqual(step.next, "escalate")
        self.assertIn("policy: the choreographer broke the rules", step.reason)

    def test_un_choreographer_qui_ecrit_dans_le_worktree_escalade_sans_rien_dire_au_dramaturg(self):
        self.begin()
        self.asks()
        self.world.dirty = " M specs/features/FEAT-007.md\n"
        step = self.advises()
        self.assertEqual(step.next, "escalate")
        self.assertIn("policy: the choreographer broke the rules", step.reason)
        self.assertEqual(self.world.sent_to_dramaturg(), [])

    def test_un_choreographer_qui_pose_une_question_au_lieu_de_repondre_escalade(self):
        self.begin()
        self.asks()
        step = self.advises(kind="question", to="director")
        self.assertEqual(step.next, "escalate")
        self.assertIn("it only answers the dramaturg's question", step.reason)

    def test_une_reponse_que_personne_n_a_demandee_est_refusee(self):
        self.begin()
        step = self.advises()
        self.assertEqual(step.next, "escalate")
        self.assertIn("it only answers", step.reason)

    def test_un_choreographer_qui_ne_peut_pas_demarrer_escalade_et_la_reprise_le_relance(self):
        self.profile(PROFILE + '\n[roles.choreographer]\ncli = "gemini-cli"\n')
        self.begin()
        step = self.asks()
        self.assertEqual(step.next, "escalate")
        self.assertIn("the choreographer could not start", step.reason)
        self.profile(PROFILE)
        self.assertEqual(self.resume().next, "wait")
        self.assertEqual(self.state()["advisor_dispatch"], "ctx_2")
        self.assertEqual(len(self.world.ran("orca", "orchestration", "worker-start")), 2)

    def test_un_choreographer_qui_s_arrete_sans_reponse_est_relance_lui_et_pas_le_dramaturg(self):
        self.begin()
        self.asks()
        self.world.inbox.append({"id": "msg_stop", "type": "escalation", "subject": "worker stopped", "body": "done",
                                 "payload": {"dispatchId": "ctx_2", "stopReason": "finished"}, "sequence": 9})
        step = ballet_workshop.receive_from_orca("BUG-004", "msg_stop", self.home, self.tools)
        self.assertEqual(step.next, "wait")
        send = self.world.ran("orca", "orchestration", "send")[0]
        self.assertEqual(send[send.index("--to") + 1], "dispatch:ctx_2")

    def test_le_statut_dit_que_le_choreographer_attend_ou_a_repondu(self):
        self.begin()
        self.asks()
        self.assertIn("choreographer: dispatch ctx_2, round 1, waiting for its answer", ballet_workshop.status("BUG-004", self.home, self.tools).render())
        self.advises()
        self.assertIn("choreographer: dispatch ctx_2, round 1, answered", ballet_workshop.status("BUG-004", self.home, self.tools).render())

    # --- le Workshop qui choisit dans le backlog ---

    BACKLOG = """# Backlog

## Next up

1. **CAP-002** · a capability is cut first.
2. `BUG-004` · stock goes negative.
3. FEAT-007 · sign in.

## Opportunities

| OPP-12 | someone | a problem | proof |
"""

    def backlog(self, text=None):
        (self.home / "specs").mkdir(exist_ok=True)
        (self.home / "specs" / "backlog.md").write_text(text or self.BACKLOG, encoding="utf-8")

    def test_sans_element_le_workshop_prend_la_premiere_ligne_de_next_up_qui_se_cadre(self):
        self.backlog()
        step = ballet_workshop.begin(None, self.home, self.tools)
        self.assertEqual(step.next, "wait")
        create = self.world.ran("orca", "worktree", "create")[0]
        self.assertEqual(create[create.index("--branch") + 1], "workshop/BUG-004")
        self.assertTrue(self.state()["picked"])
        self.assertEqual(self.journal("begin")[0]["detail"], {"item": "BUG-004", "picked": True, "request": ""})

    def test_le_choix_saute_ce_qui_a_deja_sa_session_et_ne_lit_que_next_up(self):
        self.backlog()
        self.begin()
        self.assertEqual(ballet_workshop.begin(None, self.home, self.tools).next, "wait")
        self.assertTrue(self.state("FEAT-007")["picked"])
        with self.assertRaisesRegex(ballet_workshop.WorkshopError, "no OPP, FEAT, BUG or TASK line left"):
            ballet_workshop.begin(None, self.home, self.tools)

    def test_sans_backlog_rien_n_est_choisi(self):
        with self.assertRaisesRegex(ballet_workshop.WorkshopError, "nothing to pick from"):
            ballet_workshop.begin(None, self.home, self.tools)
        self.assertFalse(self.world.ran("orca"))

    def test_ce_que_le_workshop_choisit_seul_sort_toujours_propose(self):
        self.profile(PROFILE + '\n[workshop]\nqueue_approval_skipped = ["Bug", "Feature", "Task"]\n')
        self.backlog()
        ballet_workshop.begin(None, self.home, self.tools)
        self.reports()
        self.assertEqual(self.world.statuses, ["proposed"])
        self.assertEqual(self.state()["ballet_status"], "proposed")

    def test_la_ligne_de_commande_sans_element_choisit_dans_le_backlog(self):
        self.backlog()
        code, out, _ = self.run_main("begin")
        self.assertEqual(code, 0)
        self.assertTrue(out.endswith("NEXT: wait\n"))
        self.assertIsNotNone(self.state("BUG-004"))

    def test_le_statut_dit_que_l_element_a_ete_choisi(self):
        self.backlog()
        ballet_workshop.begin(None, self.home, self.tools)
        self.assertIn("picked in the backlog", ballet_workshop.status("BUG-004", self.home, self.tools).render())

    # --- une demande hors backlog, nommée par son slug ---

    REQUEST = "Le stock passe en négatif quand on annule deux fois !"
    SLUG = "le-stock-passe-en-negatif-quand"

    def begin_request(self, request=None):
        self.world.branch = f"workshop/{self.SLUG}"
        return ballet_workshop.begin(None, self.home, self.tools, request=request or self.REQUEST)

    def captured(self, item="BUG-012"):
        return message("report", f"- Item: {item}\n- Type: Bug\n\n## Decided alone\n\n- A new bug line.\n\n## Issue draft\n\n{DRAFT}")

    def test_une_demande_nomme_sa_session_d_un_slug_sans_accents(self):
        self.assertEqual(self.begin_request().next, "wait")
        create = self.world.ran("orca", "worktree", "create")[0]
        self.assertEqual(create[create.index("--branch") + 1], f"workshop/{self.SLUG}")
        state = self.state(self.SLUG)
        self.assertEqual((state["item"], state["request"], state["picked"]), (self.SLUG, self.REQUEST, False))
        self.assertEqual(self.journal("begin")[0]["detail"], {"item": self.SLUG, "picked": False, "request": self.REQUEST})
        self.assertEqual({entry["workshop"] for entry in self.journal()}, {self.SLUG})

    def test_la_mission_demande_de_capturer_puis_de_nommer_la_ligne(self):
        self.begin_request()
        start = self.world.ran("orca", "orchestration", "worker-start")[0]
        spec = Path(start[start.index("--spec-file") + 1]).read_text()
        for expected in (self.REQUEST, "Capture it first", "- Item: <its ID>", "Frame the line you captured", f"subject `{self.SLUG}`"):
            self.assertIn(expected, spec)

    def test_la_meme_demande_deux_fois_prend_un_autre_slug(self):
        self.begin_request()
        self.begin_request()
        self.assertIsNotNone(self.state(f"{self.SLUG}-2"))

    def test_une_demande_sans_mot_est_refusee(self):
        with self.assertRaisesRegex(ballet_workshop.WorkshopError, "no word"):
            self.begin_request("!!! ???")

    def test_un_rapport_sans_la_ligne_capturee_est_renvoye(self):
        self.begin_request()
        step = self.receive("worker_done", report(), self.SLUG)
        self.assertEqual(step.next, "wait")
        self.assertIn("`- Item:`", self.world.sent_to_dramaturg()[0])

    def test_la_publication_lie_le_slug_a_la_ligne_capturee_puis_a_l_issue(self):
        self.begin_request()
        step = self.receive("worker_done", self.captured(), self.SLUG)
        self.assertEqual(step.next, "done")
        published = self.journal("published")[0]
        self.assertEqual(published["workshop"], self.SLUG)
        self.assertEqual((published["detail"]["item"], published["detail"]["issue"]), ("BUG-012", "21"))
        self.assertEqual(self.state(self.SLUG)["framed"], "BUG-012")
        self.assertIn(f"request: {self.REQUEST}, captured as BUG-012", ballet_workshop.status(self.SLUG, self.home, self.tools).render())

    def test_une_demande_suit_la_regle_du_profil_comme_un_element_nomme(self):
        self.profile(PROFILE + '\n[workshop]\nqueue_approval_skipped = ["Bug"]\n')
        self.begin_request()
        self.receive("worker_done", self.captured(), self.SLUG)
        self.assertEqual(self.world.statuses, ["ready"])

    def test_la_ligne_de_commande_ouvre_une_demande_et_la_retrouve_par_son_slug(self):
        code, out, _ = self.run_main("begin", "--request", self.REQUEST)
        self.assertEqual(code, 0)
        self.assertTrue(out.endswith("NEXT: wait\n"))
        self.begin("FEAT-007")
        code, out, _ = self.run_main("status", self.SLUG)
        self.assertEqual(code, 0)
        self.assertIn(f"Workshop {self.SLUG}: open", out)

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

    def test_un_reveil_par_le_run_traite_le_rapport_du_dramaturg(self):
        self.begin()
        self.world.run_batch = [{"id": "msg_1", "type": "worker_done", "body": report(), "payload": {"dispatchId": "ctx_1"}}]
        code, out, _ = self.run_main("receive", "BUG-004", "--run", "run_conductor")
        self.assertEqual(code, 0)
        self.assertIn("NEXT: done", out)
        self.assertEqual(self.world.ran("orca", "orchestration", "check"), [["orca", "orchestration", "check", "--run", "run_conductor", "--json"]])

    def test_le_run_ignore_les_messages_d_un_autre_worker_et_ceux_deja_traites(self):
        self.begin()
        self.receive("worker_done", message("question", "1. Which name?", to="choreographer"))
        seen = self.world.inbox[0]
        self.world.run_batch = [seen, {"id": "msg_old", "type": "worker_done", "body": "{}", "payload": {"dispatchId": "ctx_9"}}]
        step = ballet_workshop.receive_from_run("BUG-004", "run_conductor", self.home, self.tools)
        self.assertEqual(step.done, ["no new message for Workshop BUG-004 in Orca run run_conductor (2 ignored)"])

    def test_le_rapport_d_un_dramaturg_rouvert_sous_un_nouveau_dispatch_est_traite(self):
        self.begin()
        self.world.run_batch = [{"id": "msg_1", "type": "worker_done", "body": report(), "from_handle": "structworker_dramaturg",
                                 "payload": {"dispatchId": "ctx_reopened"}}]
        step = ballet_workshop.receive_from_run("BUG-004", "run_conductor", self.home, self.tools)
        self.assertEqual(step.next, "done")
        self.assertEqual(self.state()["dispatch"], "ctx_reopened")

    def test_aide_et_option_inconnue_sont_un_mauvais_usage_sans_rien_toucher(self):
        self.begin()
        before, commands = self.state(), len(self.world.commands)
        for arguments in (("--help",), ("-h",), ("receive", "--help"), ("receive", "BUG-004", "-h"), ("receive", "--bogus", "x")):
            with self.subTest(arguments=arguments):
                code, out, _ = self.run_main(*arguments)
                self.assertEqual((code, out), (2, ""))
        self.assertEqual(self.state(), before)
        self.assertEqual(len(self.world.commands), commands)

    def test_une_demande_qui_commence_par_un_tiret_n_est_pas_une_option(self):
        code, _, _ = self.run_main("begin", "--request", "-- fix the login")
        self.assertEqual(code, 0)

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

    def test_la_fin_du_workshop_est_annoncee_a_maestro_sous_le_nom_du_dossier_sans_alias(self):
        ballet_runtime.update(mailbox_terminal="term_box", mailbox_run="run_box")
        self.begin()
        self.world.said("worker_done", report(), "msg_1")
        _, out, _ = self.run_main("receive", "--message", "msg_1")
        send = [command for command in self.world.ran("orca", "orchestration", "send") if "run:run_box" in command][-1]
        self.assertEqual(send[send.index("--subject") + 1], f"{self.home.resolve().name}#BUG-004 · done")
        self.assertIn(f"- Maestro told: {self.home.resolve().name}#BUG-004 · done", out)
        self.assertTrue(out.splitlines()[-1].startswith("NEXT: done"))

    def test_une_panne_au_demarrage_est_annoncee_a_maestro_mais_pas_celle_d_un_status(self):
        ballet_runtime.update(mailbox_terminal="term_box", mailbox_run="run_box")
        self.begin()
        _, out, _ = self.run_main("begin", "BUG-004")
        self.run_main("status", "BUG-009")
        sends = [command for command in self.world.ran("orca", "orchestration", "send") if "run:run_box" in command]
        self.assertEqual([send[send.index("--subject") + 1] for send in sends],
                         [f"{self.home.resolve().name}#BUG-004 · escalate"])
        self.assertIn("NEXT: escalate the Workshop of BUG-004 is already open", out)

    def test_sans_maestro_toml_rien_n_est_envoye_a_maestro(self):
        self.begin()
        self.world.said("worker_done", report(), "msg_1")
        _, out, _ = self.run_main("receive", "--message", "msg_1")
        self.assertFalse([command for command in self.world.ran("orca", "orchestration", "send") if "--priority" in command])
        self.assertNotIn("Maestro", out)
        self.assertIn("NEXT: done", out.splitlines()[-1])

    def test_deux_sessions_tournent_cote_a_cote_sans_se_marcher_dessus(self):
        self.begin()
        self.begin("FEAT-007")
        self.assertEqual(self.state("FEAT-007")["dispatch"], "ctx_2")
        self.assertEqual(self.state()["dispatch"], "ctx_1")


if __name__ == "__main__":
    unittest.main()
