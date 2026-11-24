import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_message  # noqa: E402

HEADER = {"ballet": "message", "from": "dancer", "to": "conductor", "type": "report", "subject": "#3", "round": 1}


class BalletMessageTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def write(self, header, body="Done."):
        path = Path(self._tmp.name) / "m.md"
        path.write_text(f"{json.dumps(header)}\n\n{body}\n", encoding="utf-8")
        return path

    def test_lit_l_en_tete_et_garde_le_texte_entier(self):
        header, text = ballet_message.read_message(self.write(HEADER))
        self.assertEqual(header["type"], "report")
        self.assertTrue(text.endswith("Done.\n"))

    def test_refuse_un_en_tete_incomplet_ou_faux(self):
        for change in ({"from": "pm"}, {"type": "chat"}, {"subject": ""}, {"round": 0}, {"round": "1"}, {"ballet": "x"}):
            with self.subTest(change=change), self.assertRaises(ballet_message.MessageError):
                ballet_message.read_message(self.write({**HEADER, **change}))

    def test_un_override_du_director_est_un_message_comme_les_autres(self):
        header, text = ballet_message.read_message(self.write({**HEADER, "from": "director", "type": "override"}, "The limit is lifted."))
        self.assertEqual(header["type"], "override")
        self.assertTrue(text.endswith("The limit is lifted.\n"))

    def test_un_verdict_porte_sa_ligne_verdict(self):
        verdict = {**HEADER, "from": "critic", "type": "verdict"}
        with self.assertRaises(ballet_message.MessageError):
            ballet_message.read_message(self.write(verdict, "Looks good."))
        _, text = ballet_message.read_message(self.write(verdict, "VERDICT: APPROVED"))
        self.assertEqual(ballet_message.verdict_of(text), "APPROVED")


class NotesTest(unittest.TestCase):
    def test_les_points_de_la_section_notes(self):
        text = "VERDICT: APPROVED\n\n## Blocking\n\nNone.\n\n## Notes\n\n- `a.rs:1`: one.\n- two.\n\n## Escalation\n\n- not a note.\n"
        self.assertEqual(ballet_message.notes_of(text), ["`a.rs:1`: one.", "two."])

    def test_sans_section_notes_aucune_note(self):
        self.assertEqual(ballet_message.notes_of("VERDICT: APPROVED\n\n## Blocking\n\nNone.\n"), [])

    def test_une_section_notes_vide_n_en_a_aucune(self):
        self.assertEqual(ballet_message.notes_of("VERDICT: APPROVED\n\n## Notes\n\nNone.\n"), [])


if __name__ == "__main__":
    unittest.main()
