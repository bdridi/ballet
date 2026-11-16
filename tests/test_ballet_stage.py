import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_stage  # noqa: E402

ENTRY = {"at": "2026-11-16T12:34:38+00:00", "rehearsal": "FEAT-001.2", "event": "begin", "detail": {"first_role": "dancer"}}


class BalletStageTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name) / "antimurphy"
        self.run = self.home / ".ballet" / "run"
        self.run.mkdir(parents=True)

    def _journal(self, *lines):
        (self.run / "journal.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_montre_les_etats_et_le_journal_du_projet(self):
        (self.run / "FEAT-001.2.json").write_text(json.dumps({"id": "FEAT-001.2", "status": "done"}), encoding="utf-8")
        self._journal(json.dumps(ENTRY))
        project = ballet_stage.snapshot([self.home])["projects"][0]
        self.assertEqual(project["name"], "antimurphy")
        self.assertEqual([state["status"] for state in project["rehearsals"]], ["done"])
        self.assertEqual(project["journal"], [ENTRY])

    def test_saute_une_ligne_a_moitie_ecrite(self):
        self._journal(json.dumps(ENTRY), '{"at": "2026-11-16T12:3')
        self.assertEqual(ballet_stage.snapshot([self.home])["projects"][0]["journal"], [ENTRY])

    def test_un_projet_sans_journal_est_vide(self):
        project = ballet_stage.snapshot([self.home])["projects"][0]
        self.assertEqual((project["rehearsals"], project["journal"]), ([], []))

    def test_ne_renvoie_rien_si_rien_n_a_change(self):
        self._journal(json.dumps(ENTRY))
        version = ballet_stage.snapshot([self.home])["version"]
        self.assertEqual(ballet_stage.snapshot([self.home], since=version), {"version": version, "unchanged": True})

    def test_renvoie_tout_quand_le_journal_grandit(self):
        self._journal(json.dumps(ENTRY))
        version = ballet_stage.snapshot([self.home])["version"]
        self._journal(json.dumps(ENTRY), json.dumps({**ENTRY, "event": "wait"}))
        self.assertEqual(len(ballet_stage.snapshot([self.home], since=version)["projects"][0]["journal"]), 2)

    def test_scan_trouve_les_projets_qui_ont_un_journal(self):
        (Path(self.folder.name) / "sans-ballet").mkdir()
        self.assertEqual(ballet_stage.project_homes(self.folder.name), [self.home])

    def test_refuse_un_dossier_sans_journal(self):
        self.assertEqual(ballet_stage.main([self.folder.name]), 2)

    def test_refuse_un_port_invalide(self):
        self.assertEqual(ballet_stage.main([str(self.home), "--port", "abc"]), 2)

    def test_n_accepte_que_les_hotes_locaux(self):
        self.assertEqual([ballet_stage._is_local(host) for host in ("127.0.0.1:7700", "localhost", "evil.test:7700")], [True, True, False])


if __name__ == "__main__":
    unittest.main()
