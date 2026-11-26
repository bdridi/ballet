import contextlib
import io
import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_config  # noqa: E402
import ballet_planning  # noqa: E402
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

    def test_le_profil_dit_que_le_plan_attend_le_director(self):
        self.init()
        profile = (self.project / ".ballet" / "config.toml").read_text(encoding="utf-8")
        self.assertIn("[rehearsal]\nplan_approval = true", profile)

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

    def test_ne_pose_aucun_skill_dans_le_projet(self):
        self.init()
        self.assertEqual([p.name for p in (self.project / ".claude" / "skills").iterdir()], [".gitkeep"])

    def test_ne_touche_pas_au_gitignore_l_etat_vit_hors_du_projet(self):
        self.init()
        self.assertFalse((self.project / ".gitignore").exists())


class InitProjectGitHubTest(unittest.TestCase):
    """La planification GitHub (types et champs d'issue) suit la création des fichiers."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name)
        self.calls = []

    def main(self, *options, prepare=None):
        argv = ["init_project.py", str(self.project), "--specs", "docs/", "--proof", "make test", *options]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return init_project.main(argv, prepare_planning=prepare or self.prepared)

    def prepared(self, project_dir):
        self.calls.append(project_dir)
        return {"owner": "bdridi", "created": ["issue type Slice"], "kept": [], "incomplete": []}

    def test_prepare_les_types_et_les_champs_du_repo(self):
        self.assertEqual(self.main(), 0)
        self.assertEqual(self.calls, [str(self.project)])

    def test_cree_le_champ_size_avec_ses_options_s_et_m(self):
        """Le vrai `prepare` de la planification, devant un propriétaire vierge : le champ `Size` est créé."""
        mutations = []

        def github(arguments):
            query = next(argument for argument in arguments if argument.startswith("query="))
            if query.startswith("query=query"):
                return json.dumps({"data": {"repositoryOwner": {"__typename": "User", "id": "U", "login": "bdridi",
                                                                "issueTypes": {"nodes": []}, "issueFields": {"nodes": []}}}})
            mutations.append(query)
            return '{"data": {}}'

        with mock.patch.object(ballet_planning, "_gh_in", lambda project_dir: github):
            self.assertEqual(self.main(prepare=ballet_planning.prepare), 0)
        size = next(mutation for mutation in mutations if '"Size"' in mutation)
        self.assertIn('"S"', size)
        self.assertIn('"M"', size)

    def test_sans_github_rien_n_est_demande_a_github(self):
        self.assertEqual(self.main("--no-github"), 0)
        self.assertEqual(self.calls, [])

    def test_un_refus_de_github_echoue_sans_defaire_les_fichiers(self):
        def refused(project_dir):
            raise ballet_planning.PlanningError("no permission")
        self.assertEqual(self.main(prepare=refused), 1)
        self.assertTrue((self.project / ".ballet" / "config.toml").exists())


if __name__ == "__main__":
    unittest.main()
