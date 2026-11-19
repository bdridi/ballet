import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_program  # noqa: E402
import ballet_stage  # noqa: E402

ENTRY = {"at": "2026-11-16T12:34:38+00:00", "rehearsal": "FEAT-001.2", "event": "begin", "detail": {"first_role": "dancer"}}


class BalletStageTest(unittest.TestCase):
    def setUp(self):
        ballet_stage.TITLES.clear()
        self.read_title = ballet_stage._read_title
        ballet_stage._read_title = lambda home, issue: f"FEAT-001.2 · Issue {issue}"
        self.addCleanup(setattr, ballet_stage, "_read_title", self.read_title)
        ballet_stage.PROGRAMS.clear()
        self.ready_items = ballet_program.ready_items
        self.program = []
        ballet_program.ready_items = lambda home: self.program
        self.addCleanup(setattr, ballet_program, "ready_items", self.ready_items)
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

    def test_donne_le_titre_de_l_issue_de_chaque_rehearsal(self):
        (self.run / "FEAT-001.2.json").write_text(json.dumps({"id": "FEAT-001.2", "issue": "3"}), encoding="utf-8")
        self.assertEqual(ballet_stage.snapshot([self.home])["projects"][0]["titles"], {"FEAT-001.2": "FEAT-001.2 · Issue 3"})

    def test_ne_demande_le_titre_qu_une_fois(self):
        calls = []
        ballet_stage._read_title = lambda home, issue: calls.append(issue) or "titre"
        (self.run / "FEAT-001.2.json").write_text(json.dumps({"id": "FEAT-001.2", "issue": "3"}), encoding="utf-8")
        ballet_stage.snapshot([self.home])
        ballet_stage.snapshot([self.home])
        self.assertEqual(calls, ["3"])

    def test_donne_la_distribution_du_profil(self):
        cast = ballet_stage.snapshot([self.home])["projects"][0]["cast"]
        self.assertEqual(cast["dancer"]["cli"], "claude")

    def test_donne_les_seuils_d_escalade_du_profil(self):
        limits = ballet_stage.snapshot([self.home])["projects"][0]["limits"]
        self.assertEqual((limits["max_round_trips"], limits["max_diff_lines"]), (2, 400))

    def _session(self, item="FEAT-004", **session):
        key = item.lstrip("#")
        (self.run / f"session-{key}.json").write_text(json.dumps({"item": item, "status": "open", **session}), encoding="utf-8")

    def _queue(self):
        return ballet_stage.snapshot([self.home])["projects"][0]["queue"]

    def test_le_programme_est_celui_de_github_dans_son_ordre(self):
        self.program = [{"item": "#15", "title": "Le panier"}, {"item": "#9", "title": "Le paiement"}]
        project = ballet_stage.snapshot([self.home])["projects"][0]
        self.assertEqual([item["item"] for item in project["queue"]["program"]], ["#15", "#9"])
        self.assertEqual(project["queue_titles"], {"#15": "Le panier", "#9": "Le paiement"})
        self.assertEqual(project["queue_error"], "")

    def test_sans_session_ouverte_il_n_y_a_pas_de_session(self):
        self.assertEqual(self._queue()["sessions"], [])

    def test_une_session_ouverte_donne_son_element_ses_slices_et_sa_rehearsal_courante(self):
        self._session(mode="assisted", items=["#35", "#36"], current="FEAT-004.1",
                      played=[{"item": "FEAT-004", "rehearsal": "FEAT-004.1"}])
        project = ballet_stage.snapshot([self.home])["projects"][0]
        self.assertEqual(project["queue"]["sessions"], [{"item": "FEAT-004", "mode": "assisted", "current": "FEAT-004.1",
                          "items": ["#35", "#36"], "played": [{"item": "FEAT-004", "rehearsal": "FEAT-004.1"}]}])
        self.assertEqual(project["queue_titles"]["#35"], "FEAT-001.2 · Issue 35")

    def test_une_session_finie_n_est_plus_ouverte(self):
        self._session(item="#12", status="done", items=[], current="", played=[{"item": "#12", "rehearsal": "FEAT-001.2"}])
        self.assertEqual(self._queue()["sessions"], [])

    def test_une_session_en_pause_reste_ouverte(self):
        self._session(mode="assisted", items=["#35"], current="", played=[{"item": "#32", "rehearsal": "FEAT-004.1"}])
        self.assertEqual([session["items"] for session in self._queue()["sessions"]], [["#35"]])

    def test_les_elements_pris_par_une_session_sortent_du_programme(self):
        self.program = [{"item": "#32", "title": "La feature"}, {"item": "#35", "title": "Une slice"}, {"item": "#50", "title": "Le paiement"}]
        self._session(mode="assisted", items=["#35"], current="FEAT-004.2", played=[{"item": "#32", "rehearsal": "FEAT-004.1"}])
        self.assertEqual([item["item"] for item in self._queue()["program"]], ["#50"])

    def test_deux_sessions_ouvertes_gardent_chacune_leurs_slices_et_sortent_du_programme(self):
        self.program = [{"item": "#20", "title": "x"}, {"item": "#35", "title": "y"}, {"item": "#60", "title": "z"}]
        self._session(mode="assisted", current="FEAT-004.2", items=["#35"], played=[{"item": "#32", "rehearsal": "FEAT-004.2"}])
        self._session(item="#20", mode="autopilot", current="FEAT-005.1", items=["#44", "#45"], played=[{"item": "#20", "rehearsal": "FEAT-005.1"}])
        queue = self._queue()
        self.assertEqual(sorted(session["item"] for session in queue["sessions"]), ["#20", "FEAT-004"])
        self.assertEqual(sorted(session["items"] for session in queue["sessions"]), [["#35"], ["#44", "#45"]])
        self.assertEqual([item["item"] for item in queue["program"]], ["#60"])

    def test_une_session_a_moitie_ecrite_n_est_pas_une_session(self):
        (self.run / "session-3.json").write_text('{"item": "#3', encoding="utf-8")
        self.assertEqual(self._queue()["sessions"], [])

    def test_l_historique_joue_vient_des_begin_du_journal(self):
        begin = {**ENTRY, "detail": {"item": "#12", "plan": "auto"}}
        self._journal(json.dumps(begin), json.dumps({**ENTRY, "event": "handoff"}))
        self.assertEqual(self._queue()["played"], [{"item": "#12", "rehearsal": "FEAT-001.2"}])

    def test_une_planification_absorbee_est_jouee_par_sa_slice(self):
        (self.run / "FEAT-004.json").write_text(json.dumps({"id": "FEAT-004", "status": "done"}), encoding="utf-8")
        (self.run / "FEAT-004.1.json").write_text(json.dumps({"id": "FEAT-004.1", "planned_by": "FEAT-004"}), encoding="utf-8")
        self._journal(json.dumps({**ENTRY, "rehearsal": "FEAT-004", "detail": {"item": "FEAT-004"}}))
        self.assertEqual(self._queue()["played"], [{"item": "FEAT-004", "rehearsal": "FEAT-004.1"}])

    def test_si_github_ne_repond_pas_la_page_le_dit(self):
        def refuse(home):
            raise ballet_program.ProgramError("gh did not answer")
        ballet_program.ready_items = refuse
        project = ballet_stage.snapshot([self.home])["projects"][0]
        self.assertEqual((project["queue"]["program"], project["queue_error"]), ([], "gh did not answer"))

    def test_ne_relit_github_qu_une_fois_dans_la_duree_du_cache(self):
        calls = []
        ballet_program.ready_items = lambda home: calls.append(home) or []
        ballet_stage.snapshot([self.home])
        ballet_stage.snapshot([self.home])
        self.assertEqual(len(calls), 1)

    def test_la_version_change_quand_le_programme_change(self):
        before = ballet_stage.snapshot([self.home])["version"]
        self.program = [{"item": "#15", "title": "Le panier"}]
        ballet_stage.PROGRAMS.clear()
        self.assertNotEqual(ballet_stage.snapshot([self.home], since=before).get("unchanged"), True)

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
