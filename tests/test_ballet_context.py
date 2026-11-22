import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_context  # noqa: E402

SESSION = "5d5057ed-f4f9-4d8a-b1a9-2a09916c5139"


def assistant(fresh=2, read=0, created=0, model="claude-opus-5-5", sidechain=False):
    """Une ligne d'un transcript : un message de l'assistant et son `usage`."""
    return {"type": "assistant", "isSidechain": sidechain,
            "message": {"model": model, "usage": {"input_tokens": fresh, "cache_read_input_tokens": read,
                                                  "cache_creation_input_tokens": created, "output_tokens": 50}}}


class BalletContextTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.claude = Path(self._tmp.name) / "claude"
        environment = mock.patch.dict("os.environ", {"CLAUDE_CONFIG_DIR": str(self.claude)})
        environment.start()
        self.addCleanup(environment.stop)

    def transcript(self, lines, session=SESSION, project="-Users-me-ballet"):
        """Écrit un transcript sous `projects/<dossier>/<session>.jsonl` ; une ligne texte est écrite telle quelle."""
        path = self.claude / "projects" / project / f"{session}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join((line if isinstance(line, str) else json.dumps(line)) + "\n" for line in lines), encoding="utf-8")
        return path

    # --- retrouver le transcript ---

    def test_le_transcript_se_trouve_par_l_id_de_session_quel_que_soit_le_dossier_du_projet(self):
        self.transcript([assistant()], session="autre", project="-Users-me-antimurphy")
        wanted = self.transcript([assistant()], project="-Users-me-autre-chose")
        self.assertEqual(ballet_context.transcript_of(SESSION), wanted)

    def test_sans_transcript_pour_cet_id_rien_n_est_rendu(self):
        self.transcript([assistant()], session="autre")
        self.assertIsNone(ballet_context.transcript_of(SESSION))

    def test_sans_dossier_de_projets_rien_n_est_rendu(self):
        self.assertIsNone(ballet_context.transcript_of(SESSION))

    def test_le_dossier_de_claude_est_celui_de_config_dir_sinon_dot_claude(self):
        with mock.patch.dict("os.environ", clear=False) as environment:
            environment.pop("CLAUDE_CONFIG_DIR")
            self.assertEqual(ballet_context.claude_home(), Path.home() / ".claude")
        self.assertEqual(ballet_context.claude_home(), self.claude)

    def test_un_id_de_session_qui_sort_du_dossier_est_refuse(self):
        self.transcript([assistant()])
        for wrong in ("../" + SESSION, "*", "a/b", ""):
            with self.subTest(session=wrong):
                self.assertIsNone(ballet_context.transcript_of(wrong))

    # --- la taille du contexte ---

    def test_le_contexte_est_la_somme_des_trois_entrees_du_dernier_message(self):
        path = self.transcript([assistant(2, 25_815, 21_527), assistant(4, 135_146, 14), assistant(2, 135_563, 446)])
        self.assertEqual(ballet_context.used_tokens(path), 2 + 135_563 + 446)

    def test_la_sortie_du_message_n_entre_pas_dans_le_contexte(self):
        path = self.transcript([assistant(2, 100, 10)])
        self.assertEqual(ballet_context.used_tokens(path), 112)

    def test_un_message_synthetique_a_usage_nul_est_ignore(self):
        path = self.transcript([assistant(2, 90_000, 0), assistant(0, 0, 0, model="<synthetic>")])
        self.assertEqual(ballet_context.used_tokens(path), 90_002)

    def test_un_message_de_sous_agent_est_ignore(self):
        path = self.transcript([assistant(2, 90_000, 0), assistant(2, 500_000, 0, sidechain=True)])
        self.assertEqual(ballet_context.used_tokens(path), 90_002)

    def test_une_derniere_ligne_coupee_pendant_l_ecriture_est_sautee(self):
        path = self.transcript([assistant(2, 90_000, 0), '{"type": "assistant", "message": {"usage": {"input_to'])
        self.assertEqual(ballet_context.used_tokens(path), 90_002)

    def test_les_lignes_qui_ne_sont_pas_des_messages_de_l_assistant_sont_ignorees(self):
        path = self.transcript([{"type": "user", "message": {"content": "hello"}}, assistant(2, 40_000, 0),
                                {"type": "system", "subtype": "turn_duration"}])
        self.assertEqual(ballet_context.used_tokens(path), 40_002)

    def test_apres_une_compaction_le_dernier_message_fait_foi(self):
        boundary = {"type": "system", "subtype": "compact_boundary", "compactMetadata": {"trigger": "auto", "preTokens": 329_231, "postTokens": 20_675}}
        path = self.transcript([assistant(2, 328_000, 238), boundary, assistant(2, 89_000, 772)])
        self.assertEqual(ballet_context.used_tokens(path), 89_774)

    def test_sans_message_de_l_assistant_le_contexte_est_inconnu(self):
        path = self.transcript([{"type": "user", "message": {"content": "hello"}}])
        self.assertIsNone(ballet_context.used_tokens(path))


if __name__ == "__main__":
    unittest.main()
