import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_config  # noqa: E402
import init_project  # noqa: E402


class InitProjectTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name) / "Mon Projet"
        self.project.mkdir()

    def init(self):
        return init_project.init_project(self.project, specs="docs/", proof="make test")

    def test_cree_les_fichiers_attendus(self):
        self.init()
        for name in (".ballet/config.toml", "AGENTS.md", "CLAUDE.md", ".claude/skills"):
            self.assertTrue((self.project / name).exists(), name)
        self.assertEqual((self.project / "CLAUDE.md").read_text(), "@AGENTS.md\n")

    def test_le_lien_agents_pointe_vers_les_skills_claude(self):
        self.init()
        link = self.project / ".agents" / "skills"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), (self.project / ".claude" / "skills").resolve())

    def test_le_dossier_des_skills_est_suivi_par_git(self):
        self.init()
        self.assertTrue((self.project / ".claude" / "skills" / ".gitkeep").exists())

    def test_la_config_generee_est_valide(self):
        self.init()
        config = ballet_config.effective_config(self.project)
        self.assertEqual(ballet_config.find_problems(config), [])
        self.assertIn("mon-projet", config["repos"])

    def test_une_preuve_avec_des_guillemets_reste_du_toml_valide(self):
        init_project.init_project(self.project, specs="docs/", proof='echo "a" && make test')
        config = ballet_config.effective_config(self.project)
        self.assertEqual(config["repos"]["mon-projet"]["proof"], 'echo "a" && make test')

    def test_ne_remplace_aucun_fichier_existant(self):
        (self.project / "AGENTS.md").write_text("à moi")
        report = self.init()
        self.assertEqual((self.project / "AGENTS.md").read_text(), "à moi")
        self.assertIn(self.project.resolve() / "AGENTS.md", report["kept"])

    def test_deuxieme_passage_ne_cree_rien(self):
        self.init()
        self.assertEqual(self.init()["created"], [])


if __name__ == "__main__":
    unittest.main()
