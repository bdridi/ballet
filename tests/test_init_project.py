import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_la_langue_des_specs_choisie_est_ecrite_dans_le_profil(self):
        init_project.init_project(self.project, specs="docs/", proof="make test", specs_language="fr")
        config = ballet_config.effective_config(self.project)
        self.assertEqual(config["project"]["specs_language"], "fr")

    def test_ne_remplace_aucun_fichier_existant(self):
        (self.project / "AGENTS.md").write_text("à moi")
        report = self.init()
        self.assertEqual((self.project / "AGENTS.md").read_text(), "à moi")
        self.assertIn(self.project.resolve() / "AGENTS.md", report["kept"])

    def test_deuxieme_passage_ne_cree_rien(self):
        self.init()
        self.assertEqual(self.init()["created"], [])

    def test_pose_le_skill_reset_ballet_qui_lance_le_script_du_clone(self):
        clone = Path(__file__).resolve().parent.parent
        with mock.patch.object(init_project, "CLAUDE_MARKETPLACES", self.project / "absent.json"):
            self.init()
        skill = (self.project / ".claude" / "skills" / "reset-ballet" / "SKILL.md").read_text()
        self.assertIn("name: reset-ballet", skill)
        self.assertIn(str(clone / "scripts" / "reset_plugin.py"), skill)

    def test_le_clone_est_pris_dans_la_marketplace_locale_plutot_que_dans_le_cache(self):
        clone = Path(self._tmp.name) / "clone"
        (clone / ".claude-plugin").mkdir(parents=True)
        (clone / ".claude-plugin" / "plugin.json").write_text('{"name": "ballet"}')
        registry = Path(self._tmp.name) / "known_marketplaces.json"
        registry.write_text(json.dumps({"ballet-local": {"source": {"source": "directory", "path": str(clone)}}}))
        with mock.patch.object(init_project, "CLAUDE_MARKETPLACES", registry):
            self.init()
        skill = (self.project / ".claude" / "skills" / "reset-ballet" / "SKILL.md").read_text()
        self.assertIn(str(clone / "scripts" / "reset_plugin.py"), skill)


if __name__ == "__main__":
    unittest.main()
