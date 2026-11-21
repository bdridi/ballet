import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_program  # noqa: E402


def blocker(number, state="OPEN", reason=None, repo="acme/shop"):
    """Un bloqueur, tel que `blockedBy` le rend."""
    return {"number": number, "state": state, "stateReason": reason, "url": f"https://github.com/{repo}/issues/{number}",
            "repository": {"nameWithOwner": repo}}


def issue(number, kind="Feature", status="ready", priority="", mode="", created="2026-11-01T10:00:00Z", title=None,
          blocked_by=(), total_blocked_by=None):
    values = [("Ballet status", status), ("Priority", priority), ("Rehearsal mode", mode)]
    return {
        "number": number, "title": title or f"Issue {number}", "url": f"https://github.com/acme/shop/issues/{number}",
        "createdAt": created,
        "issueType": {"name": kind} if kind else None,
        "issueFieldValues": {"nodes": [{"name": value, "field": {"name": field}} for field, value in values if value]},
        "blockedBy": {"totalCount": len(blocked_by) if total_blocked_by is None else total_blocked_by, "nodes": list(blocked_by)},
    }


def page(*issues, next_cursor=""):
    return json.dumps({"data": {"repository": {"nameWithOwner": "acme/shop", "issues": {
        "pageInfo": {"hasNextPage": bool(next_cursor), "endCursor": next_cursor}, "nodes": list(issues)}}}})


class FakeGitHub:
    """Rejoue les pages de réponse dans l'ordre et garde les appels."""

    def __init__(self, *pages):
        self.pages = list(pages)
        self.calls = []

    def __call__(self, arguments):
        self.calls.append(arguments)
        return self.pages.pop(0)


class ReadyItemsTest(unittest.TestCase):
    def test_ne_garde_que_les_feature_bug_et_task_prets(self):
        github = FakeGitHub(page(issue(1), issue(2, "Bug"), issue(3, "Task"), issue(4, "Slice"), issue(5, status="in-rehearsal"),
                                 issue(6, status="proposed"), issue(7, kind=None), issue(8, status="")))
        self.assertEqual([item["item"] for item in ballet_program.ready_items(run=github)], ["#1", "#2", "#3"])

    def test_trie_par_priorite_puis_par_anciennete(self):
        github = FakeGitHub(page(
            issue(1, priority="Low", created="2026-11-01T10:00:00Z"),
            issue(2, created="2026-11-02T10:00:00Z"),
            issue(3, priority="Urgent", created="2026-11-05T10:00:00Z"),
            issue(4, priority="High", created="2026-11-04T10:00:00Z"),
            issue(5, priority="High", created="2026-11-03T10:00:00Z"),
        ))
        self.assertEqual([item["item"] for item in ballet_program.ready_items(run=github)], ["#3", "#5", "#4", "#1", "#2"])

    def test_donne_le_titre_le_type_la_priorite_et_le_mode(self):
        github = FakeGitHub(page(issue(12, "Bug", priority="High", mode="autopilot", title="Le panier se vide")))
        item = ballet_program.ready_items(run=github)[0]
        self.assertEqual((item["title"], item["type"], item["priority"], item["mode"]), ("Le panier se vide", "Bug", "High", "autopilot"))

    def test_donne_le_lien_de_l_issue(self):
        item = ballet_program.ready_items(run=FakeGitHub(page(issue(12))))[0]
        self.assertEqual(item["url"], "https://github.com/acme/shop/issues/12")

    def test_un_champ_non_pose_est_vide(self):
        item = ballet_program.ready_items(run=FakeGitHub(page(issue(1))))[0]
        self.assertEqual((item["priority"], item["mode"]), ("", ""))

    def test_lit_toutes_les_pages(self):
        github = FakeGitHub(page(issue(1), next_cursor="CURSOR-1"), page(issue(2)))
        self.assertEqual([item["item"] for item in ballet_program.ready_items(run=github)], ["#1", "#2"])
        self.assertIn("after=CURSOR-1", github.calls[1])
        self.assertNotIn("after=CURSOR-1", github.calls[0])

    def test_un_programme_vide_reste_une_liste_vide(self):
        self.assertEqual(ballet_program.ready_items(run=FakeGitHub(page())), [])

    def test_une_erreur_de_github_n_est_pas_un_programme_vide(self):
        refused = json.dumps({"errors": [{"message": "Could not resolve to a Repository"}]})
        with self.assertRaisesRegex(ballet_program.ProgramError, "Could not resolve"):
            ballet_program.ready_items(run=FakeGitHub(refused))


class DependenciesTest(unittest.TestCase):
    """Les liens « Blocked by » de GitHub : un seul calcul, dans `ready_items`."""

    def items(self, *issues):
        return {item["item"]: item for item in ballet_program.ready_items(run=FakeGitHub(page(*issues)))}

    def test_la_requete_lit_les_bloqueurs_dans_le_meme_appel_que_la_file(self):
        github = FakeGitHub(page(issue(1), issue(2, blocked_by=[blocker(1)])))
        ballet_program.ready_items(run=github)
        self.assertEqual(len(github.calls), 1)
        query = next(argument for argument in github.calls[0] if argument.startswith("query="))
        self.assertIn("blockedBy(first: 20)", query)
        self.assertIn("blockedBy(first: 20) { totalCount nodes {", query)
        self.assertNotIn("issueDependenciesSummary", query)   # son compte a plusieurs secondes de retard : blockedBy.totalCount est à jour
        self.assertIn("nameWithOwner", query)

    def test_un_element_sans_bloqueur_est_lancable(self):
        item = self.items(issue(1))["#1"]
        self.assertEqual((item["blocked_by"], item["launchable"], item["doubt"]), ([], True, ""))

    def test_un_element_porte_ses_bloqueurs_encore_ouverts(self):
        item = self.items(issue(1), issue(2, blocked_by=[blocker(1)]))["#2"]
        self.assertEqual(item["blocked_by"], [{"item": "#1", "number": 1, "repo": "acme/shop", "url": "https://github.com/acme/shop/issues/1"}])
        self.assertFalse(item["launchable"])
        self.assertTrue(ballet_program.waits(item))

    def test_un_bloqueur_ferme_ne_bloque_plus(self):
        item = self.items(issue(2, blocked_by=[blocker(1, "CLOSED", "COMPLETED")]))["#2"]
        self.assertEqual((item["blocked_by"], item["launchable"], item["doubt"]), ([], True, ""))

    def test_seuls_les_bloqueurs_ouverts_sont_gardes_parmi_plusieurs(self):
        item = self.items(issue(3, blocked_by=[blocker(1, "CLOSED", "COMPLETED"), blocker(2)]))["#3"]
        self.assertEqual([found["item"] for found in item["blocked_by"]], ["#2"])

    def test_un_bloqueur_d_un_autre_repo_est_nomme_avec_son_repo(self):
        item = self.items(issue(2, blocked_by=[blocker(5, repo="acme/api")]))["#2"]
        self.assertEqual((item["blocked_by"][0]["item"], item["blocked_by"][0]["repo"]), ("acme/api#5", "acme/api"))
        self.assertTrue(ballet_program.waits(item))

    def test_la_feature_2_attend_la_feature_1_quand_les_deux_sont_pretes(self):
        items = self.items(issue(1), issue(2, blocked_by=[blocker(1)]))
        self.assertEqual([item["item"] for item in items.values() if item["launchable"]], ["#1"])

    def test_un_bloqueur_ferme_comme_not_planned_est_un_doute_et_non_une_attente(self):
        item = self.items(issue(2, blocked_by=[blocker(1, "CLOSED", "NOT_PLANNED")]))["#2"]
        self.assertEqual(item["doubt"], "blocker #1 was closed as not planned, not delivered")
        self.assertEqual((item["blocked_by"], item["launchable"], ballet_program.waits(item)), ([], True, False))

    def test_un_bloqueur_ferme_comme_doublon_est_un_doute(self):
        item = self.items(issue(2, blocked_by=[blocker(1, "CLOSED", "DUPLICATE")]))["#2"]
        self.assertIn("closed as duplicate", item["doubt"])

    def test_un_cycle_de_dependances_est_un_doute_pour_chacun_de_ses_membres(self):
        items = self.items(issue(1, blocked_by=[blocker(2)]), issue(2, blocked_by=[blocker(1)]))
        self.assertEqual(items["#1"]["doubt"], "dependency cycle: #1 → #2 → #1")
        self.assertEqual(items["#2"]["doubt"], "dependency cycle: #2 → #1 → #2")
        self.assertFalse(ballet_program.waits(items["#1"]))

    def test_un_element_derriere_un_cycle_attend_sans_doute(self):
        items = self.items(issue(1, blocked_by=[blocker(2)]), issue(2, blocked_by=[blocker(1)]), issue(3, blocked_by=[blocker(1)]))
        self.assertEqual(items["#3"]["doubt"], "")
        self.assertTrue(ballet_program.waits(items["#3"]))

    def test_un_bloqueur_illisible_est_un_doute(self):
        item = self.items(issue(2, blocked_by=[], total_blocked_by=1))["#2"]
        self.assertIn("1 of its 1 blockers cannot be read", item["doubt"])
        self.assertFalse(ballet_program.waits(item))

    def test_un_bloqueur_illisible_a_cote_d_un_bloqueur_ouvert_reste_un_doute(self):
        item = self.items(issue(2, blocked_by=[blocker(1)], total_blocked_by=2))["#2"]
        self.assertEqual([found["item"] for found in item["blocked_by"]], ["#1"])
        self.assertIn("1 of its 2 blockers cannot be read", item["doubt"])
        self.assertFalse(ballet_program.waits(item))

    def test_un_bloqueur_nul_dans_la_reponse_est_ignore_et_compte_comme_illisible(self):
        item = self.items(issue(2, blocked_by=[None], total_blocked_by=1))["#2"]
        self.assertIn("cannot be read", item["doubt"])

    def test_le_compte_en_retard_de_issue_dependencies_summary_ne_fait_pas_un_doute(self):
        stale = issue(2)
        stale["issueDependenciesSummary"] = {"totalBlockedBy": 1}   # GitHub le met à jour plusieurs secondes après un `unblock`
        item = self.items(stale)["#2"]
        self.assertEqual((item["blocked_by"], item["doubt"]), ([], ""))

    def test_dependencies_of_rend_les_dependances_d_une_issue_ouverte_meme_non_prete(self):
        github = FakeGitHub(page(issue(1), issue(2, status="in-rehearsal", blocked_by=[blocker(1)])))
        found = ballet_program.dependencies_of("2", run=github)
        self.assertEqual([blocker["item"] for blocker in found["blocked_by"]], ["#1"])

    def test_dependencies_of_une_issue_fermee_ou_inconnue_n_a_rien(self):
        found = ballet_program.dependencies_of("9", run=FakeGitHub(page(issue(1))))
        self.assertEqual(found, {"blocked_by": [], "doubt": ""})

    def test_le_programme_affiche_les_elements_bloques(self):
        items = ballet_program.ready_items(run=FakeGitHub(page(issue(1), issue(2, blocked_by=[blocker(1)]))))
        out = io.StringIO()
        with redirect_stdout(out):
            ballet_program.print_program(items)
        self.assertIn("[blocked by #1]", out.getvalue())
        self.assertEqual(out.getvalue().count("blocked by"), 1)


if __name__ == "__main__":
    unittest.main()
