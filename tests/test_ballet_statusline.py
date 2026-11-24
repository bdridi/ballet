import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_capacity  # noqa: E402
import ballet_statusline  # noqa: E402

RESET = 1795532400   # 2026-11-24 15:00 UTC
PAYLOAD = {"model": {"id": "claude-sonnet-5-5"},
           "rate_limits": {"five_hour": {"used_percentage": 93.5, "resets_at": RESET},
                           "seven_day": {"used_percentage": 12, "resets_at": "2026-11-28T09:00:00Z"}}}


class BalletStatuslineTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.state = self.root / "ballet-home"
        self.config_dir = self.root / "claude"
        self.config_dir.mkdir()

    def user_statusline(self, command):
        settings = {"statusLine": {"type": "command", "command": command}}
        (self.config_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    def run_statusline(self, payload=PAYLOAD):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return ballet_statusline.run(text, self.state, self.config_dir)

    def captured(self):
        return ballet_capacity.read("claude", 30, self.state)

    # --- ce que Claude Code envoie à sa statusline

    def test_la_capture_de_claude_garde_le_pourcentage_utilise_et_le_reset_en_date(self):
        rate_limits = {**PAYLOAD["rate_limits"], "seven_day_opus": {"used_percentage": 99, "resets_at": RESET}}
        self.assertEqual(ballet_statusline.windows_of(rate_limits), {
            "five_hour": {"used_percent": 93.5, "resets_at": "2026-11-24T15:00:00+00:00"},
            "seven_day": {"used_percent": 12.0, "resets_at": "2026-11-28T09:00:00+00:00"}})

    def test_la_forme_oauth_utilization_est_lue_comme_used_percentage(self):
        windows = ballet_statusline.windows_of({"five_hour": {"utilization": 40, "resets_at": RESET}})
        self.assertEqual(windows["five_hour"]["used_percent"], 40.0)

    def test_un_reset_en_millisecondes_est_lu_comme_un_reset_en_secondes(self):
        windows = ballet_statusline.windows_of({"five_hour": {"used_percentage": 1, "resets_at": RESET * 1000}})
        self.assertEqual(windows["five_hour"]["resets_at"], "2026-11-24T15:00:00+00:00")

    def test_un_pourcentage_hors_de_0_a_100_est_ramene_dans_l_intervalle(self):
        windows = ballet_statusline.windows_of({"five_hour": {"used_percentage": 130, "resets_at": RESET},
                                                "seven_day": {"used_percentage": -3, "resets_at": RESET}})
        self.assertEqual((windows["five_hour"]["used_percent"], windows["seven_day"]["used_percent"]), (100.0, 0.0))

    def test_sans_rate_limits_une_cle_d_api_la_capture_est_vide(self):
        self.assertEqual(ballet_statusline.windows_of(None), {})
        self.assertEqual(ballet_statusline.windows_of("n'importe quoi"), {})

    def test_une_fenetre_sans_pourcentage_est_ignoree(self):
        self.assertEqual(ballet_statusline.windows_of({"five_hour": {"resets_at": RESET}, "seven_day": None}), {})

    def test_un_reset_illisible_laisse_la_fenetre_avec_un_reset_vide(self):
        windows = ballet_statusline.windows_of({"five_hour": {"used_percentage": 50, "resets_at": "bientôt"}})
        self.assertEqual(windows["five_hour"], {"used_percent": 50.0, "resets_at": ""})

    # --- la commande

    def test_la_commande_note_les_fenetres_et_rend_une_ligne_courte(self):
        line = self.run_statusline()
        self.assertEqual(line, "5h 94% · 7d 12%")
        self.assertEqual(self.captured()["five_hour"]["used_percent"], 93.5)
        self.assertEqual(self.captured()["seven_day"]["resets_at"], "2026-11-28T09:00:00+00:00")

    def test_sans_rate_limits_rien_n_est_note_et_la_ligne_est_vide(self):
        self.assertEqual(self.run_statusline({"model": {"id": "x"}, "rate_limits": None}), "")
        self.assertFalse((self.state / "capacity").exists())

    def test_une_entree_illisible_ne_leve_jamais(self):
        for payload in ("", "pas du json", "[1, 2]", "null", '{"rate_limits": 3}'):
            with self.subTest(payload=payload):
                self.assertEqual(self.run_statusline(payload), "")

    def test_un_dossier_d_etat_illisible_ne_leve_pas_non_plus(self):
        blocked = self.root / "blocked"
        blocked.write_text("un fichier là où il faudrait un dossier", encoding="utf-8")
        self.assertEqual(ballet_statusline.run(json.dumps(PAYLOAD), blocked, self.config_dir), "5h 94% · 7d 12%")

    # --- la statusline de l'utilisateur est chaînée, pas remplacée

    def test_la_statusline_de_l_utilisateur_recoit_la_meme_entree_et_son_affichage_est_gardé(self):
        self.user_statusline("cat >/dev/null; echo 'orca statusline'")
        self.assertEqual(self.run_statusline(), "orca statusline")
        self.assertEqual(self.captured()["five_hour"]["used_percent"], 93.5)

    def test_l_ancienne_commande_lit_le_json_tel_que_claude_l_a_envoye(self):
        self.user_statusline("cat")
        self.assertEqual(json.loads(self.run_statusline()), PAYLOAD)

    def test_une_ancienne_commande_qui_echoue_laisse_la_ligne_de_ballet(self):
        self.user_statusline("exit 3")
        self.assertEqual(self.run_statusline(), "5h 94% · 7d 12%")

    def test_une_ancienne_commande_introuvable_laisse_la_ligne_de_ballet(self):
        self.user_statusline("commande-qui-n-existe-pas-ballet")
        self.assertEqual(self.run_statusline(), "5h 94% · 7d 12%")

    def test_la_note_est_prise_meme_quand_l_ancienne_commande_echoue(self):
        self.user_statusline("exit 3")
        self.run_statusline()
        self.assertEqual(self.captured()["five_hour"]["used_percent"], 93.5)

    def test_une_statusline_qui_n_est_pas_une_commande_n_est_pas_chainee(self):
        (self.config_dir / "settings.json").write_text(json.dumps({"statusLine": {"type": "text", "command": "echo non"}}), encoding="utf-8")
        self.assertEqual(self.run_statusline(), "5h 94% · 7d 12%")

    def test_des_reglages_illisibles_ne_sont_pas_chaines(self):
        (self.config_dir / "settings.json").write_text("{pas du json", encoding="utf-8")
        self.assertEqual(self.run_statusline(), "5h 94% · 7d 12%")

    def test_la_commande_de_ballet_elle_meme_n_est_jamais_chainee(self):
        self.user_statusline("python3 /x/ballet_statusline.py")
        self.assertEqual(self.run_statusline(), "5h 94% · 7d 12%")

    # --- la ligne de commande

    def test_main_lit_l_entree_standard_ecrit_la_ligne_et_sort_avec_0(self):
        out = io.StringIO()
        code = ballet_statusline.main(["ballet_statusline.py"], stdin=io.StringIO(json.dumps(PAYLOAD)), stdout=out,
                                      state=self.state, config_dir=self.config_dir)
        self.assertEqual((code, out.getvalue()), (0, "5h 94% · 7d 12%\n"))

    def test_main_sort_avec_0_meme_sur_une_entree_cassee(self):
        out = io.StringIO()
        self.assertEqual(ballet_statusline.main(["x"], stdin=io.StringIO("\x00\x01"), stdout=out, state=self.state, config_dir=self.config_dir), 0)


if __name__ == "__main__":
    unittest.main()
