import json
import shlex
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_session  # noqa: E402


class BalletSessionTest(unittest.TestCase):
    def test_une_session_allegee_n_a_aucun_serveur_mcp_et_les_outils_de_son_role(self):
        self.assertEqual(ballet_session.lean_options("Bash,Read"),
                         ["--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--tools", "Bash,Read"])

    def test_les_deux_roles_gardent_l_outil_des_skills_pour_charger_ceux_de_ballet(self):
        for tools in (ballet_session.CONDUCTOR_TOOLS, ballet_session.MAESTRO_TOOLS):
            self.assertIn("Skill", tools.split(","))
            self.assertIn("Bash", tools.split(","))

    def test_la_commande_porte_le_cache_d_une_heure_apres_les_variables_donnees(self):
        command = ballet_session.with_environment("claude --remote-control x", {"BALLET_HOME": "/a b"})
        self.assertEqual(shlex.split(command),
                         ["BALLET_HOME=/a b", "CLAUDE_CODE_PROMPT_CACHE_TTL=1h", "claude", "--remote-control", "x"])

    def test_sans_variable_donnee_la_commande_ne_porte_que_le_cache(self):
        self.assertEqual(ballet_session.with_environment("claude", {}), "CLAUDE_CODE_PROMPT_CACHE_TTL=1h claude")

    def test_la_statusline_de_ballet_se_branche_par_settings_sur_la_commande_du_script(self):
        options = ballet_session.statusline_options()
        self.assertEqual(options[0], "--settings")
        status_line = json.loads(options[1])["statusLine"]
        self.assertEqual(status_line["type"], "command")
        script = Path(ballet_session.__file__).with_name("ballet_statusline.py")
        self.assertEqual(shlex.split(status_line["command"]), ["python3", str(script)])
        self.assertTrue(script.is_file())

    def test_la_commande_de_la_statusline_survit_a_un_chemin_avec_des_espaces(self):
        with mock.patch.object(ballet_session, "STATUSLINE_SCRIPT", Path("/Users/a b/plugin/scripts/ballet_statusline.py")):
            command = json.loads(ballet_session.statusline_options()[1])["statusLine"]["command"]
        self.assertEqual(shlex.split(command), ["python3", "/Users/a b/plugin/scripts/ballet_statusline.py"])


if __name__ == "__main__":
    unittest.main()
