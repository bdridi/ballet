import shlex
import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
