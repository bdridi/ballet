import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_config  # noqa: E402

VALID_PROJECT = """
    [project]
    specs = "specs/"
    rules = ["tdd"]

    [repos.app]
    path = "."
    proof = "make test"
"""


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name)

    def write_project_config(self, text):
        path = self.project / ".ballet" / "config.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")

    def problems(self):
        config = ballet_config.effective_config(self.project)
        return ballet_config.find_problems(config)

    def assertProblem(self, fragment):
        found = self.problems()
        self.assertTrue(any(fragment in p for p in found), f"« {fragment} » absent de {found}")

    # --- fusion

    def test_sans_fichier_projet_les_defauts_s_appliquent(self):
        config = ballet_config.effective_config(self.project)
        self.assertEqual(config["roles"]["critic"]["cli"], "grok")
        self.assertEqual(config["escalation"]["max_round_trips"], 2)

    def test_la_surcharge_remplace_une_cle_et_le_reste_herite(self):
        self.write_project_config(VALID_PROJECT + '\n[roles.dancer]\ncli = "mistral-vibe"\n')
        config = ballet_config.effective_config(self.project)
        self.assertEqual(config["roles"]["dancer"]["cli"], "mistral-vibe")
        self.assertEqual(config["roles"]["critic"]["cli"], "grok")
        self.assertEqual(config["escalation"]["max_diff_lines"], 400)

    def test_toml_invalide_est_refuse(self):
        self.write_project_config("ceci n'est pas du toml")
        with self.assertRaises(ballet_config.ConfigError):
            ballet_config.effective_config(self.project)

    # --- config valide et champs obligatoires

    def test_config_valide_sans_probleme(self):
        self.write_project_config(VALID_PROJECT)
        self.assertEqual(self.problems(), [])

    def test_sans_fichier_projet_le_demarrage_est_refuse(self):
        self.assertProblem("init-project")

    def test_repo_sans_preuve_est_refuse(self):
        self.write_project_config('[project]\nspecs = "specs/"\n[repos.app]\npath = "."\n')
        self.assertProblem("[repos.app] proof manquant")

    def test_merge_inconnu_est_refuse(self):
        self.write_project_config(VALID_PROJECT.replace('specs = "specs/"', 'specs = "specs/"\nmerge = "rebase"'))
        self.assertProblem("merge doit valoir")

    # --- needs

    def test_needs_vers_un_repo_inconnu_est_refuse(self):
        self.write_project_config(VALID_PROJECT + '\n[repos.web]\npath = "../web"\nproof = "x"\nneeds = ["api"]\n')
        self.assertProblem("repo inconnu « api »")

    def test_cycle_dans_needs_est_refuse(self):
        self.write_project_config(
            '[project]\nspecs = "s/"\n'
            '[repos.a]\npath = "a"\nproof = "x"\nneeds = ["b"]\n'
            '[repos.b]\npath = "b"\nproof = "x"\nneeds = ["a"]\n'
        )
        self.assertProblem("cycle dans needs")

    def test_dependances_en_diamant_ne_sont_pas_un_cycle(self):
        self.write_project_config(
            '[project]\nspecs = "s/"\n'
            '[repos.base]\npath = "b"\nproof = "x"\n'
            '[repos.left]\npath = "l"\nproof = "x"\nneeds = ["base"]\n'
            '[repos.right]\npath = "r"\nproof = "x"\nneeds = ["base"]\n'
            '[repos.top]\npath = "t"\nproof = "x"\nneeds = ["left", "right"]\n'
        )
        self.assertEqual(self.problems(), [])

    # --- rôles

    def test_critic_et_dancer_sur_le_meme_cli_sont_refuses(self):
        self.write_project_config(VALID_PROJECT + '\n[roles.dancer]\ncli = "grok"\n')
        self.assertProblem("Critic ≠ Dancer")

    def test_meme_cli_avec_deux_modeles_explicites_differents_est_accepte(self):
        self.write_project_config(
            VALID_PROJECT
            + '\n[roles.dancer]\ncli = "claude"\nmodel = "a"\n[roles.critic]\ncli = "claude"\nmodel = "b"\n'
        )
        self.assertEqual(self.problems(), [])

    def test_meme_cli_avec_un_seul_modele_explicite_est_refuse(self):
        self.write_project_config(
            VALID_PROJECT + '\n[roles.dancer]\ncli = "claude"\nmodel = "a"\n[roles.critic]\ncli = "claude"\n'
        )
        self.assertProblem("Critic ≠ Dancer")

    def test_cli_inconnu_est_refuse(self):
        self.write_project_config(VALID_PROJECT + '\n[roles.dancer]\ncli = "gpt-3"\n')
        self.assertProblem("cli inconnu « gpt-3 »")

    def test_role_inconnu_est_refuse(self):
        self.write_project_config(VALID_PROJECT + '\n[roles.pianist]\ncli = "claude"\n')
        self.assertProblem("rôle inconnu")

    # --- règles et seuils

    def test_regle_inconnue_est_refusee(self):
        self.write_project_config(VALID_PROJECT.replace('["tdd"]', '["tdd", "magie"]'))
        self.assertProblem("règle inconnue « magie »")

    def test_seuil_invalide_est_refuse(self):
        self.write_project_config(VALID_PROJECT + "\n[escalation]\nmax_round_trips = 0\n")
        self.assertProblem("max_round_trips doit être un entier positif")


if __name__ == "__main__":
    unittest.main()
