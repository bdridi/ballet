import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_github  # noqa: E402

ISSUE_BODY = "## Context\n\nWhy.\n\n## Plan\n\n<!-- empty -->\n\n## Notes\n\nKeep me.\n"


class FakeGh:
    def __init__(self, body=ISSUE_BODY):
        self.body = body
        self.calls = []

    def __call__(self, arguments):
        self.calls.append(arguments)
        if arguments[:2] == ["issue", "view"]:
            return json.dumps({"body": self.body})
        if arguments[:2] == ["issue", "create"]:
            return "https://github.com/o/r/issues/42\n"
        if arguments[:2] == ["issue", "edit"]:
            self.body = arguments[arguments.index("--body") + 1]
        return ""


class BalletGitHubTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def file(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_publie_un_brouillon_avec_son_titre(self):
        gh = FakeGh()
        draft = self.file("d.md", "# FEAT-001 · Sign in\n\n## Context\n\nWhy.\n")
        self.assertEqual(ballet_github.publish_issue(draft, run=gh), "42")
        create = gh.calls[0]
        self.assertEqual(create[create.index("--title") + 1], "FEAT-001 · Sign in")
        self.assertTrue(create[create.index("--body") + 1].startswith("## Context"))

    def test_refuse_un_brouillon_sans_titre(self):
        with self.assertRaises(ballet_github.GitHubError):
            ballet_github.publish_issue(self.file("d.md", "no title\n"), run=FakeGh())

    def test_ecrit_le_plan_dans_sa_section_sans_toucher_au_reste(self):
        gh = FakeGh()
        plan = self.file("p.md", "## Plan\n\n### Decisions\n\n- a → b.\n")
        ballet_github.write_plan("#7", plan, run=gh)
        self.assertIn("## Plan\n\n### Decisions\n\n- a → b.\n\n## Notes\n\nKeep me.", gh.body)
        self.assertNotIn("<!-- empty -->", gh.body)
        self.assertEqual(gh.body.count("## Plan"), 1)

    def test_refuse_une_issue_sans_section_plan(self):
        gh = FakeGh(body="## Context\n")
        with self.assertRaises(ballet_github.GitHubError):
            ballet_github.write_plan("7", self.file("p.md", "x"), run=gh)

    def test_refuse_un_brouillon_complet_a_la_place_du_plan(self):
        gh = FakeGh()
        draft = self.file("d.md", "# FEAT-001 · Sign in\n\n## Plan\n\n- a → b.\n")
        with self.assertRaisesRegex(ballet_github.GitHubError, "publish"):
            ballet_github.write_plan("7", draft, run=gh)
        self.assertFalse([call for call in gh.calls if call[:2] == ["issue", "edit"]])

    def test_un_brouillon_sans_titre_renvoie_vers_plan(self):
        with self.assertRaisesRegex(ballet_github.GitHubError, "plan"):
            ballet_github.publish_issue(self.file("d.md", "## Plan\n\n- a → b.\n"), run=FakeGh())

    def test_une_slice_pointe_vers_sa_parente(self):
        gh = FakeGh()
        draft = self.file("s.md", "# FEAT-001.1 · Skeleton\n\n## Plan\n\nx\n")
        self.assertEqual(ballet_github.publish_slice("#7", draft, run=gh), "42")
        body = gh.calls[0][gh.calls[0].index("--body") + 1]
        self.assertTrue(body.startswith("Part of #7\n"))

    def test_refuse_un_numero_invalide(self):
        with self.assertRaises(ballet_github.GitHubError):
            ballet_github.read_issue("abc", run=FakeGh())

    def test_refuse_une_operation_inconnue(self):
        self.assertEqual(ballet_github.main(["x", "delete", "7"]), 1)


if __name__ == "__main__":
    unittest.main()
