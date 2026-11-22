import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_conductors  # noqa: E402
import ballet_db  # noqa: E402
import ballet_maestro  # noqa: E402
import ballet_store  # noqa: E402


class BalletStoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.home = root / "shop"
        self.home.mkdir()
        environment = mock.patch.dict("os.environ", {"BALLET_HOME": str(root / "ballet-home")})
        environment.start()
        self.addCleanup(environment.stop)

    def log(self, event, detail=None, key="FEAT-001.2", scope="rehearsal", conductor="#3"):
        ballet_store.log(self.home, scope, key, event, detail or {}, conductor=conductor)

    def nodes(self):
        """(genre, nom, joué par, en cours ?, issue), dans l'ordre de leur début."""
        with ballet_db.reading() as connection:
            rows = connection.execute("SELECT * FROM nodes ORDER BY started_at, rowid").fetchall()
        return [(row["kind"], row["name"], row["runner"], row["ended_at"] is None, row["outcome"]) for row in rows]

    def events_of(self, kind, name):
        with ballet_db.reading() as connection:
            rows = connection.execute("SELECT e.phase, e.kind FROM events e JOIN nodes n ON n.id = e.node "
                                      "WHERE n.kind = ? AND n.name = ? ORDER BY e.id", (kind, name)).fetchall()
        return [(row["phase"], row["kind"]) for row in rows]

    # --- les états ---

    def test_un_etat_se_relit_tel_qu_il_a_ete_ecrit_et_se_remplace(self):
        ballet_store.save(self.home, "rehearsal", {"id": "FEAT-001.2", "status": "open", "rounds": {"a": 1}})
        ballet_store.save(self.home, "rehearsal", {"id": "FEAT-001.2", "status": "done", "rounds": {"a": 2}})
        self.assertEqual(ballet_store.load(self.home, "rehearsal", "FEAT-001.2"), {"id": "FEAT-001.2", "status": "done", "rounds": {"a": 2}})
        self.assertIsNone(ballet_store.load(self.home, "rehearsal", "FEAT-009"))

    def test_le_projet_est_l_alias_de_maestro_toml_sinon_le_nom_du_dossier(self):
        self.assertEqual(ballet_store.project_of(self.home), "shop")
        ballet_maestro.add_project("boutique", str(self.home))
        self.assertEqual(ballet_store.project_of(self.home), "boutique")

    def test_deux_projets_ne_voient_pas_leurs_etats(self):
        other = self.home.parent / "other"
        other.mkdir()
        ballet_store.save(self.home, "session", {"item": "#3"})
        self.assertEqual(ballet_store.all_of(other, "session"), [])
        self.assertTrue(ballet_store.known(self.home))
        self.assertFalse(ballet_store.known(other))

    def test_le_dossier_de_travail_est_hors_du_projet(self):
        folder = ballet_store.work_dir(self.home)
        self.assertEqual(folder, Path(self._tmp.name) / "ballet-home" / "projects" / "shop")
        self.assertTrue(folder.is_dir())
        self.assertEqual(list(self.home.iterdir()), [])

    def test_drop_oublie_l_etat_et_garde_le_journal(self):
        ballet_store.save(self.home, "session", {"item": "#3"})
        self.log("begin")
        self.assertEqual(ballet_store.main(["ballet_store.py", "drop", "session", "#3"], home=self.home), 0)
        self.assertIsNone(ballet_store.load(self.home, "session", "#3"))
        self.assertEqual(len(ballet_store.journal(self.home, "rehearsal")), 1)
        self.assertEqual(ballet_store.main(["ballet_store.py", "drop", "session", "#3"], home=self.home), 1)
        self.assertEqual(ballet_store.main(["ballet_store.py", "drop", "queue", "x"], home=self.home), 2)

    # --- les nœuds ---

    def test_une_rehearsal_jouee_donne_ses_noeuds_du_debut_a_la_fin(self):
        self.log("begin", {"item": "#3"})
        self.log("handoff", {"role": "dancer", "how": "start", "text": "go"})
        self.log("message", {"from": "dancer", "to": "conductor", "type": "report"})
        self.log("proof-start", {"command": "make test"})
        self.log("proof-end", {"passed": True})
        self.log("diff-size", {"counted": 12})
        self.log("handoff", {"role": "critic", "how": "start", "text": "review"})
        self.log("message", {"from": "critic", "to": "conductor", "type": "verdict"})
        self.log("done", {"reason": "merged"})
        self.assertEqual(self.nodes(), [("rehearsal", "FEAT-001.2", "script", False, "ok"),
                                        ("turn", "dancer", "agent", False, "ok"),
                                        ("proof", "make test", "script", False, "ok"),
                                        ("turn", "critic", "agent", False, "ok")])

    def test_un_noeud_en_cours_se_voit_tant_qu_il_n_a_pas_fini(self):
        self.log("begin")
        self.log("handoff", {"role": "dancer", "how": "start"})
        self.log("message", {"from": "dancer", "to": "conductor", "type": "report"})
        self.log("mutation-start", {"tool": "cargo-mutants"})
        running = [(kind, name) for kind, name, _, open_, _ in self.nodes() if open_]
        self.assertEqual(running, [("rehearsal", "FEAT-001.2"), ("mutation", "cargo-mutants")])
        self.log("mutation-end", {"tool": "cargo-mutants", "passed": False, "timed_out": True})
        self.assertEqual(self.nodes()[-1], ("mutation", "cargo-mutants", "script", False, "timeout"))

    def test_l_escalade_ouvre_l_attente_du_director_que_l_evenement_suivant_ferme(self):
        self.log("begin")
        self.log("escalate", {"reason": "plan to review"})
        self.assertEqual(self.nodes()[-1], ("director", "director", "human", True, None))
        self.log("message", {"from": "director", "to": "choreographer", "type": "approve"})
        self.assertEqual(self.nodes()[-1], ("director", "director", "human", False, "ok"))

    def test_un_rappel_ou_une_relance_ne_rouvre_pas_le_tour(self):
        self.log("begin")
        self.log("handoff", {"role": "critic", "how": "start"})
        self.log("handoff", {"role": "critic", "how": "nudge"})
        self.log("nudge", {"role": "critic"})
        self.assertEqual([node[:2] for node in self.nodes()], [("rehearsal", "FEAT-001.2"), ("turn", "critic")])
        self.assertEqual(self.events_of("turn", "critic"), [("start", "handoff"), ("mark", "handoff"), ("mark", "nudge")])

    def test_une_question_finit_le_tour_et_la_reponse_en_ouvre_un_autre(self):
        self.log("begin")
        self.log("handoff", {"role": "dancer", "how": "start"})
        self.log("message", {"from": "dancer", "to": "choreographer", "type": "question"})
        self.log("handoff", {"role": "choreographer", "how": "start"})
        self.log("message", {"from": "choreographer", "to": "dancer", "type": "answer"})
        self.log("handoff", {"role": "dancer", "how": "reply"})
        turns = [(name, open_) for kind, name, _, open_, _ in self.nodes() if kind == "turn"]
        self.assertEqual(turns, [("dancer", False), ("choreographer", False), ("dancer", True)])

    def test_l_arret_ferme_tout_ce_qui_tournait(self):
        self.log("begin")
        self.log("handoff", {"role": "dancer", "how": "start"})
        self.log("stopped", {"reason": "by Maestro"})
        self.assertEqual([(kind, open_, outcome) for kind, _, _, open_, outcome in self.nodes()],
                         [("rehearsal", False, "stopped"), ("turn", False, "stopped")])

    def test_une_planification_qui_passe_la_main_a_sa_slice_est_finie(self):
        self.log("begin", key="FEAT-002")
        self.log("handoff", {"role": "choreographer", "how": "start"}, key="FEAT-002")
        self.log("message", {"from": "choreographer", "to": "conductor", "type": "report"}, key="FEAT-002")
        self.log("handover", {"to": "FEAT-002.1"}, key="FEAT-002")
        self.assertEqual(self.nodes()[0], ("rehearsal", "FEAT-002", "script", False, "ok"))

    def test_la_rehearsal_est_sous_le_noeud_de_son_conductor(self):
        ballet_conductors.record_launch("shop#3", "shop", "3", "rehearsal", "term_1")
        self.log("begin")
        with ballet_db.reading() as connection:
            rehearsal = connection.execute("SELECT parent, conductor FROM nodes WHERE kind = 'rehearsal'").fetchone()
            conductor = connection.execute("SELECT node FROM conductors WHERE id = 'shop#3'").fetchone()["node"]
        self.assertEqual((rehearsal["parent"], rehearsal["conductor"]), (conductor, "shop#3"))

    def test_une_rehearsal_rejouee_apres_sa_fin_a_un_nouveau_noeud(self):
        self.log("begin")
        self.log("done")
        self.log("frictions", {"frictions": []})
        self.log("begin")
        self.assertEqual([(kind, open_) for kind, _, _, open_, _ in self.nodes()], [("rehearsal", False), ("rehearsal", True)])
        self.assertEqual(self.events_of("rehearsal", "FEAT-001.2"), [("start", "begin"), ("end", "done"), ("mark", "frictions"), ("start", "begin")])

    # --- le journal ---

    def test_le_journal_rend_les_evenements_tels_que_les_scripts_les_ont_ecrits(self):
        self.log("begin", {"item": "#3"})
        self.log("handoff", {"role": "dancer", "how": "start"})
        self.log("escalate", {"reason": "x"})
        self.log("message", {"from": "director", "to": "dancer", "type": "answer"})
        self.log("stopped", {"reason": "y"})
        self.log("begin", key="FEAT-002")
        entries = ballet_store.journal_of(self.home, "rehearsal", "FEAT-001.2")
        self.assertEqual([(entry["rehearsal"], entry["event"]) for entry in entries],
                         [("FEAT-001.2", "begin"), ("FEAT-001.2", "handoff"), ("FEAT-001.2", "escalate"),
                          ("FEAT-001.2", "message"), ("FEAT-001.2", "stopped")])
        self.assertEqual(entries[0]["detail"], {"item": "#3"})
        self.assertEqual([entry["rehearsal"] for entry in ballet_store.journal(self.home, "rehearsal")][-1], "FEAT-002")

    def test_le_journal_des_workshops_est_a_part(self):
        self.log("begin")
        self.log("begin", scope="workshop", key="BUG-004")
        self.assertEqual([entry["workshop"] for entry in ballet_store.journal(self.home, "workshop")], ["BUG-004"])
        self.assertEqual(len(ballet_store.journal(self.home, "rehearsal")), 1)

    def test_un_evenement_sans_debut_connu_range_quand_meme_sa_boucle(self):
        self.log("wait", {"reason": ""})
        self.assertEqual(self.nodes(), [("rehearsal", "FEAT-001.2", "script", True, None)])
        self.assertEqual([entry["event"] for entry in ballet_store.journal(self.home, "rehearsal")], ["wait"])


if __name__ == "__main__":
    unittest.main()
