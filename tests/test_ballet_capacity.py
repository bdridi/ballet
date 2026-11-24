import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_capacity  # noqa: E402

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
RESET = "2026-11-24T15:00:00+00:00"


class BalletCapacityTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state = Path(self._tmp.name)

    def captured(self, minutes_ago=1, five_hour=42.0, seven_day=10.0):
        """Ce que la statusline de Claude a noté, il y a `minutes_ago` minutes."""
        ballet_capacity.record("claude", {"five_hour": {"used_percent": five_hour, "resets_at": RESET},
                                          "seven_day": {"used_percent": seven_day, "resets_at": RESET}},
                               self.state, now=NOW - timedelta(minutes=minutes_ago))

    def read(self, stale_after_minutes=30):
        return ballet_capacity.read("claude", stale_after_minutes, self.state, now=NOW)

    # --- la lecture

    def test_chaque_fenetre_rend_son_pourcentage_son_reset_et_l_instant_de_la_capture(self):
        self.captured(minutes_ago=2)
        found = self.read()
        self.assertEqual(found["five_hour"], {"used_percent": 42.0, "resets_at": RESET, "captured_at": "2026-11-24T11:58:00+00:00"})
        self.assertEqual(found["seven_day"]["used_percent"], 10.0)

    def test_sans_capture_chaque_fenetre_est_inconnue(self):
        self.assertEqual(self.read(), {"five_hour": None, "seven_day": None})

    def test_un_chiffre_plus_vieux_que_le_delai_est_inconnu(self):
        self.captured(minutes_ago=31)
        self.assertEqual(self.read(stale_after_minutes=30), {"five_hour": None, "seven_day": None})

    def test_un_chiffre_pile_au_delai_est_encore_valable(self):
        self.captured(minutes_ago=30)
        self.assertIsNotNone(self.read(stale_after_minutes=30)["five_hour"])

    def test_une_fenetre_absente_de_la_capture_est_inconnue_sans_gener_l_autre(self):
        ballet_capacity.record("claude", {"five_hour": {"used_percent": 50, "resets_at": RESET}}, self.state, now=NOW)
        found = self.read()
        self.assertEqual(found["five_hour"]["used_percent"], 50)
        self.assertIsNone(found["seven_day"])

    def test_un_fichier_illisible_est_inconnu_jamais_une_erreur(self):
        path = self.state / "capacity" / "claude.json"
        path.parent.mkdir(parents=True)
        path.write_text("{pas du json", encoding="utf-8")
        self.assertEqual(self.read(), {"five_hour": None, "seven_day": None})

    def test_un_fichier_a_la_date_illisible_est_inconnu(self):
        path = self.state / "capacity" / "claude.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"captured_at": "hier", "windows": {"five_hour": {"used_percent": 99, "resets_at": RESET}}}),
                        encoding="utf-8")
        self.assertEqual(self.read(), {"five_hour": None, "seven_day": None})

    def test_chaque_harnais_a_son_fichier(self):
        self.captured()
        self.assertEqual(ballet_capacity.read("vibe", 30, self.state, now=NOW), {"five_hour": None, "seven_day": None})

    def test_une_capture_vide_n_ecrit_rien(self):
        ballet_capacity.record("claude", {}, self.state, now=NOW)
        self.assertFalse((self.state / "capacity").exists())

    # --- le seuil et sa marge

    def test_le_seuil_est_franchi_des_qu_il_est_atteint(self):
        self.assertEqual([ballet_capacity.is_above(used, 90) for used in (89.9, 90, 100)], [False, True, True])

    def test_un_chiffre_inconnu_ou_une_sonde_coupee_ne_franchit_rien(self):
        self.assertFalse(ballet_capacity.is_above(None, 90))
        self.assertFalse(ballet_capacity.is_above(99, 0))

    def test_la_redescente_demande_cinq_points_de_marge(self):
        self.assertEqual([ballet_capacity.is_back_under(used, 90) for used in (90, 85, 84.9, 10)], [False, False, True, True])

    def test_un_chiffre_inconnu_ou_une_sonde_coupee_est_une_redescente(self):
        self.assertTrue(ballet_capacity.is_back_under(None, 90))
        self.assertTrue(ballet_capacity.is_back_under(99, 0))

    def test_un_petit_seuil_redescend_quand_meme_a_un_chiffre_realiste(self):
        self.assertEqual([ballet_capacity.is_back_under(used, 3) for used in (2, 0.5)], [False, True])

    # --- la config

    def test_les_defauts_du_plugin_sont_90_90_et_30_minutes(self):
        self.assertEqual(ballet_capacity.settings({}), {"five_hour_threshold": 90, "seven_day_threshold": 90, "stale_after_minutes": 30})

    def test_la_machine_surcharge_cle_par_cle(self):
        found = ballet_capacity.settings({"capacity": {"five_hour_threshold": 80}})
        self.assertEqual(found, {"five_hour_threshold": 80, "seven_day_threshold": 90, "stale_after_minutes": 30})

    def test_un_seuil_a_zero_coupe_la_sonde_de_sa_fenetre(self):
        self.assertEqual(ballet_capacity.settings({"capacity": {"seven_day_threshold": 0}})["seven_day_threshold"], 0)

    def test_un_seuil_hors_de_0_a_100_est_refuse(self):
        for value in (101, -1, 90.5, "90", True):
            with self.subTest(value=value), self.assertRaises(ballet_capacity.CapacityError) as refused:
                ballet_capacity.settings({"capacity": {"five_hour_threshold": value}})
            self.assertIn("five_hour_threshold", str(refused.exception))

    def test_le_delai_de_peremption_est_un_entier_d_au_moins_une_minute(self):
        for value in (0, -5, 1.5, "30"):
            with self.subTest(value=value), self.assertRaises(ballet_capacity.CapacityError) as refused:
                ballet_capacity.settings({"capacity": {"stale_after_minutes": value}})
            self.assertIn("stale_after_minutes", str(refused.exception))

    def test_une_cle_inconnue_est_refusee(self):
        with self.assertRaises(ballet_capacity.CapacityError) as refused:
            ballet_capacity.settings({"capacity": {"five_hour_treshold": 80}})
        self.assertIn("five_hour_treshold", str(refused.exception))

    def test_les_problemes_d_une_table_sont_listes_en_anglais_pour_la_verification_de_config(self):
        self.assertEqual(ballet_capacity.problems({"five_hour_threshold": 90, "seven_day_threshold": 0, "stale_after_minutes": 30}), [])
        found = ballet_capacity.problems({"five_hour_threshold": 120, "seven_day_threshold": 90, "stale_after_minutes": 0})
        self.assertEqual(len(found), 2)
        self.assertTrue(all(problem.startswith("[capacity] ") for problem in found))


if __name__ == "__main__":
    unittest.main()
