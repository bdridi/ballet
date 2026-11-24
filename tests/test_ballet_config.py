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
        self.assertEqual(config["roles"]["critic"], {"cli": "claude", "model": "opus"})
        self.assertEqual(config["roles"]["dancer"], {"cli": "claude", "model": "sonnet"})
        self.assertEqual(config["escalation"]["max_round_trips"], 2)

    def test_la_surcharge_remplace_une_cle_et_le_reste_herite(self):
        self.write_project_config(VALID_PROJECT + '\n[roles.dancer]\nmodel = "haiku"\n')
        config = ballet_config.effective_config(self.project)
        self.assertEqual(config["roles"]["dancer"], {"cli": "claude", "model": "haiku"})
        self.assertEqual(config["roles"]["critic"], {"cli": "claude", "model": "opus"})
        self.assertEqual(config["escalation"]["max_diff_lines"], 1500)

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
        self.assertProblem("[repos.app] proof missing")

    def test_les_specs_sont_en_anglais_par_defaut(self):
        self.write_project_config(VALID_PROJECT)
        self.assertEqual(ballet_config.effective_config(self.project)["project"]["specs_language"], "en")

    def test_les_adr_sont_dans_docs_adr_par_defaut(self):
        self.write_project_config(VALID_PROJECT)
        self.assertEqual(ballet_config.effective_config(self.project)["project"]["adr"], "docs/ADR/")

    def test_un_dossier_adr_vide_est_refuse(self):
        self.write_project_config(VALID_PROJECT.replace('specs = "specs/"', 'specs = "specs/"\nadr = ""'))
        self.assertProblem("[project] adr must be a folder path")

    def test_une_langue_des_specs_qui_n_est_pas_un_code_est_refusee(self):
        self.write_project_config(VALID_PROJECT.replace('specs = "specs/"', 'specs = "specs/"\nspecs_language = "français"'))
        self.assertProblem("specs_language must be a language code")

    # --- needs

    def test_needs_vers_un_repo_inconnu_est_refuse(self):
        self.write_project_config(VALID_PROJECT + '\n[repos.web]\npath = "../web"\nproof = "x"\nneeds = ["api"]\n')
        self.assertProblem("unknown repo 'api'")

    def test_cycle_dans_needs_est_refuse(self):
        self.write_project_config(
            '[project]\nspecs = "s/"\n'
            '[repos.a]\npath = "a"\nproof = "x"\nneeds = ["b"]\n'
            '[repos.b]\npath = "b"\nproof = "x"\nneeds = ["a"]\n'
        )
        self.assertProblem("cycle in needs")

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

    def test_les_defauts_respectent_critic_different_de_dancer(self):
        self.write_project_config(VALID_PROJECT)
        self.assertEqual(self.problems(), [])

    def test_critic_et_dancer_sur_le_meme_modele_sont_refuses(self):
        self.write_project_config(VALID_PROJECT + '\n[roles.dancer]\nmodel = "opus"\n')
        self.assertProblem("Critic ≠ Dancer")

    def test_critic_et_dancer_sur_des_cli_differents_sont_acceptes(self):
        self.write_project_config(VALID_PROJECT + '\n[roles.dancer]\ncli = "mistral-vibe"\nmodel = "devstral"\n')
        self.assertEqual(self.problems(), [])

    def test_meme_cli_avec_deux_modeles_explicites_differents_est_accepte(self):
        self.write_project_config(
            VALID_PROJECT
            + '\n[roles.dancer]\ncli = "claude"\nmodel = "a"\n[roles.critic]\ncli = "claude"\nmodel = "b"\n'
        )
        self.assertEqual(self.problems(), [])

    def test_meme_cli_avec_un_seul_modele_explicite_est_refuse(self):
        self.write_project_config(
            VALID_PROJECT + '\n[roles.dancer]\nmodel = "a"\n[roles.critic]\nmodel = ""\n'
        )
        self.assertProblem("Critic ≠ Dancer")

    def test_cli_inconnu_est_refuse(self):
        self.write_project_config(VALID_PROJECT + '\n[roles.dancer]\ncli = "gpt-3"\n')
        self.assertProblem("unknown cli 'gpt-3'")

    def test_role_inconnu_est_refuse(self):
        self.write_project_config(VALID_PROJECT + '\n[roles.pianist]\ncli = "claude"\n')
        self.assertProblem("unknown role")

    # --- règles et seuils

    def test_regle_inconnue_est_refusee(self):
        self.write_project_config(VALID_PROJECT.replace('["tdd"]', '["tdd", "magie"]'))
        self.assertProblem("unknown rule 'magie'")

    def test_les_defauts_de_la_politique_sont_valides(self):
        self.write_project_config(VALID_PROJECT)
        self.assertEqual(self.problems(), [])

    def test_aucun_role_ne_peut_ecrire_le_profil(self):
        self.write_project_config(VALID_PROJECT + '\n[policy]\nforbidden_zones = ["CLAUDE.md"]\n')
        self.assertProblem("[policy.roles.dancer] lets the dancer write .ballet/config.toml")

    def test_une_extension_du_projet_qui_ouvre_le_profil_est_refusee(self):
        self.write_project_config(VALID_PROJECT + '\n[policy.roles.choreographer]\nextra_writes = [".ballet/*"]\n')
        self.assertProblem("[policy.roles.choreographer] lets the choreographer write .ballet/config.toml")

    def test_un_perimetre_mal_forme_est_refuse(self):
        self.write_project_config(VALID_PROJECT + '\n[policy.roles.dancer]\nextra_except = "migrations/*"\n\n[policy.roles.mime]\nwrites = []\n')
        self.assertProblem("[policy.roles.dancer] extra_except must be a list of globs")
        self.assertProblem("[policy.roles.mime]: unknown role")

    def test_un_langage_de_test_sans_groupe_ou_mal_forme_est_refuse(self):
        self.write_project_config(VALID_PROJECT + "\n[policy.test_names.go]\nextensions = ['.go']\npattern = 'func Test'\n"
                                  "\n[policy.test_names.kotlin]\nextensions = ['.kt']\npattern = '(unclosed'\n")
        self.assertProblem("[policy.test_names.go] pattern needs a group")
        self.assertProblem("[policy.test_names.kotlin] pattern is not a valid regular expression")

    def test_seuil_invalide_est_refuse(self):
        self.write_project_config(VALID_PROJECT + "\n[escalation]\nmax_round_trips = 0\n")
        self.assertProblem("max_round_trips must be a positive integer")

    def test_plafond_d_echanges_invalide_est_refuse(self):
        self.write_project_config(VALID_PROJECT + "\n[escalation]\nmax_exchange_rounds = 0\n")
        self.assertProblem("max_exchange_rounds must be a positive integer")

    def test_attente_de_la_ci_invalide_est_refusee(self):
        self.write_project_config(VALID_PROJECT + "\n[escalation]\nci_wait_seconds = 0\n")
        self.assertProblem("ci_wait_seconds must be a positive integer")

    def test_mode_strict_qui_n_est_pas_un_booleen_est_refuse(self):
        self.write_project_config(VALID_PROJECT + '\n[escalation]\nmax_diff_strict = "yes"\n')
        self.assertProblem("max_diff_strict must be true or false")

    def test_par_defaut_le_plan_attend_le_director_et_ce_n_est_plus_une_escalade(self):
        self.write_project_config(VALID_PROJECT)
        config = ballet_config.effective_config(self.project)
        self.assertIs(config["rehearsal"]["plan_approval"], True)
        self.assertNotIn("plan_approval", config["escalation"])

    def test_l_approbation_du_plan_qui_n_est_pas_un_booleen_est_refusee(self):
        self.write_project_config(VALID_PROJECT + '\n[rehearsal]\nplan_approval = "no"\n')
        self.assertProblem("[rehearsal] plan_approval must be true or false")

    def test_par_defaut_le_workshop_autopilot_passe_tout_par_le_director(self):
        self.write_project_config(VALID_PROJECT)
        config = ballet_config.effective_config(self.project)
        self.assertEqual(config["workshop"]["queue_approval_skipped"], [])

    def test_un_type_de_travail_peut_sauter_l_acceptation_du_director(self):
        self.write_project_config(VALID_PROJECT + '\n[workshop]\nqueue_approval_skipped = ["Bug", "Task"]\n')
        self.assertEqual(ballet_config.find_problems(ballet_config.effective_config(self.project)), [])

    def test_un_type_inconnu_ou_une_liste_mal_formee_sont_refuses_pour_l_acceptation(self):
        for value in ('["Epic"]', '"Bug"'):
            with self.subTest(value=value):
                self.write_project_config(VALID_PROJECT + f"\n[workshop]\nqueue_approval_skipped = {value}\n")
                self.assertProblem("[workshop] queue_approval_skipped must be a list of issue types among Feature, Bug, Task")

    def test_sans_modele_de_conductor_le_profil_reste_valide_et_laisse_celui_de_la_machine(self):
        self.write_project_config(VALID_PROJECT)
        config = ballet_config.effective_config(self.project)
        self.assertEqual(("model" in config.get("conductor", {}), ballet_config.find_problems(config)), (False, []))

    def test_un_projet_choisit_le_modele_de_son_conductor(self):
        self.write_project_config(VALID_PROJECT + '\n[conductor]\nmodel = "sonnet"\n')
        config = ballet_config.effective_config(self.project)
        self.assertEqual((config["conductor"]["model"], ballet_config.find_problems(config)), ("sonnet", []))

    def test_un_modele_de_conductor_vide_ou_qui_n_est_pas_un_texte_est_refuse(self):
        for value in ('""', "3", "true"):
            with self.subTest(value=value):
                self.write_project_config(VALID_PROJECT + f"\n[conductor]\nmodel = {value}\n")
                self.assertProblem("[conductor] model must be a model name")

    def test_la_sonde_de_capacite_a_ses_defauts_et_reste_valide(self):
        self.write_project_config(VALID_PROJECT)
        config = ballet_config.effective_config(self.project)
        self.assertEqual(config["capacity"], {"five_hour_threshold": 90, "seven_day_threshold": 90, "stale_after_minutes": 30})
        self.assertEqual(ballet_config.find_problems(config), [])

    def test_un_seuil_de_capacite_a_zero_coupe_la_sonde_sans_etre_un_probleme(self):
        self.write_project_config(VALID_PROJECT + "\n[capacity]\nfive_hour_threshold = 0\n")
        self.assertEqual(self.problems(), [])

    def test_une_sonde_de_capacite_mal_reglee_est_refusee(self):
        self.write_project_config(VALID_PROJECT + "\n[capacity]\nseven_day_threshold = 150\nstale_after_minutes = 0\n")
        self.assertProblem("[capacity] seven_day_threshold must be a whole number from 0 to 100")
        self.assertProblem("[capacity] stale_after_minutes must be a whole number, 1 or more")

    def test_exclusions_qui_ne_sont_pas_une_liste_sont_refusees(self):
        self.write_project_config(VALID_PROJECT + '\n[escalation]\ndiff_exclude = "*.lock"\n')
        self.assertProblem("diff_exclude must be a list of globs")

    def test_par_defaut_la_taille_ne_bloque_pas_et_exclut_les_lockfiles(self):
        self.write_project_config(VALID_PROJECT)
        escalation = ballet_config.effective_config(self.project)["escalation"]
        self.assertFalse(escalation["max_diff_strict"])
        self.assertIn("*.lock", escalation["diff_exclude"])

    # --- la mutation

    def test_par_defaut_la_mutation_est_activee_avec_une_heure_de_budget(self):
        self.write_project_config(VALID_PROJECT)
        self.assertEqual(ballet_config.effective_config(self.project)["mutation"], {"enabled": True, "timeout_seconds": 3600})

    def test_un_drapeau_ou_un_budget_de_mutation_invalide_est_refuse(self):
        self.write_project_config(VALID_PROJECT + '\n[mutation]\nenabled = "no"\ntimeout_seconds = 0\n')
        self.assertProblem("[mutation] enabled must be true or false")
        self.assertProblem("[mutation] timeout_seconds must be a positive integer")

    def test_une_entree_de_mutation_complete_est_valide(self):
        self.write_project_config(VALID_PROJECT + MUTATION_TOOL)
        self.assertEqual(self.problems(), [])

    def test_une_entree_de_mutation_incomplete_est_refusee(self):
        self.write_project_config(VALID_PROJECT + '\n[[repos.app.mutation]]\nname = "cargo-mutants"\npaths = "crates/*"\n'
                                  'report = { path = "out.json", format = "mystery" }\n')
        self.assertProblem("[[repos.app.mutation]] cargo-mutants: command must be a non-empty string")
        self.assertProblem("[[repos.app.mutation]] cargo-mutants: config must be a non-empty string")
        self.assertProblem("[[repos.app.mutation]] cargo-mutants: report format must be one of cargo-mutants")
        self.assertProblem("[[repos.app.mutation]] cargo-mutants: paths must be a list of globs")

    def test_deux_outils_de_mutation_du_meme_nom_sont_refuses(self):
        self.write_project_config(VALID_PROJECT + MUTATION_TOOL + MUTATION_TOOL)
        self.assertProblem("each tool needs its own name")


MUTATION_TOOL = """
[[repos.app.mutation]]
name = "cargo-mutants"
command = "cargo mutants --in-diff {diff}"
config = ".cargo/mutants.toml"
report = { path = "mutants.out/outcomes.json", format = "cargo-mutants" }
"""


if __name__ == "__main__":
    unittest.main()
