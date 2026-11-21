import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_program  # noqa: E402


def issue(number, kind="Feature", status="ready", priority="", mode="", created="2026-11-01T10:00:00Z", title=None):
    values = [("Ballet status", status), ("Priority", priority), ("Rehearsal mode", mode)]
    return {
        "number": number, "title": title or f"Issue {number}", "url": f"https://github.com/acme/shop/issues/{number}",
        "createdAt": created,
        "issueType": {"name": kind} if kind else None,
        "issueFieldValues": {"nodes": [{"name": value, "field": {"name": field}} for field, value in values if value]},
    }


def page(*issues, next_cursor=""):
    return json.dumps({"data": {"repository": {"issues": {
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


if __name__ == "__main__":
    unittest.main()
