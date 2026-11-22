import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_db  # noqa: E402
import ballet_stage  # noqa: E402
import ballet_store  # noqa: E402


class BalletStageTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.home = root / "shop"
        self.home.mkdir()
        environment = mock.patch.dict("os.environ", {"BALLET_HOME": str(root / "ballet-home")})
        environment.start()
        self.addCleanup(environment.stop)
        for cache in (ballet_stage.TITLES, ballet_stage.ASKED, ballet_stage.REPOS):
            cache.clear()
        reader = mock.patch.object(ballet_stage, "_read_title", lambda home, issue: f"FEAT-001.2 · Issue {issue}")
        reader.start()
        self.addCleanup(reader.stop)

    def log(self, event, detail=None, key="FEAT-001.2", scope="rehearsal", conductor="FEAT-001.2"):
        ballet_store.log(self.home, scope, key, event, detail or {}, conductor=conductor)

    def stage(self):
        return ballet_stage.snapshot()["stage"]

    def play(self, key="FEAT-001.2"):
        return next(play for play in self.stage()["plays"] if play["key"] == key)

    def wait_for_titles(self):
        ballet_stage._TITLE_READERS.submit(lambda: None).result()

    def set_ready(self, items):
        with ballet_db.writing() as connection:
            connection.execute("INSERT OR REPLACE INTO ready (project, items, seen_at) VALUES ('shop', ?, '2026-11-22T20:00:00+00:00')",
                               (json.dumps(items),))

    # --- les représentations ---

    def test_une_rehearsal_jouee_donne_sa_representation_et_son_arbre(self):
        self.log("begin", {"item": "#3"})
        self.log("handoff", {"role": "dancer", "how": "start"})
        self.log("message", {"from": "dancer", "to": "conductor", "type": "report", "round": 1, "text": "done"})
        snapshot = ballet_stage.snapshot()
        play = snapshot["stage"]["plays"][0]
        self.assertEqual((play["project"], play["kind"], play["key"], play["type"]), ("shop", "rehearsal", "FEAT-001.2", "Slice"))
        self.assertEqual((play["parent"], play["counts"]["turn"], play["counts"]["message"]), ("FEAT-001", 1, 1))
        tree = snapshot["plays"][play["node"]]
        self.assertEqual([event["kind"] for event in tree["marks"]], ["begin"])
        self.assertEqual([(node["kind"], node["name"]) for node in tree["nodes"]], [("turn", "dancer")])

    def test_l_etat_donne_la_pr_les_allers_retours_et_le_diff(self):
        ballet_store.save(self.home, "rehearsal", {"id": "FEAT-001.2", "issue": "3", "pull_request": "9", "round_trips": 1, "size": {"counted": 812}})
        self.log("begin")
        play = self.play()
        self.assertEqual((play["issue"], play["pr"], play["round_trips"], play["diff"], play["planning"]), ("3", "9", 1, 812, False))

    def test_un_long_message_est_coupe(self):
        self.log("begin")
        self.log("handoff", {"role": "dancer", "how": "start"})
        self.log("message", {"from": "dancer", "to": "conductor", "type": "report", "text": "x" * 5000})
        tree = ballet_stage.snapshot()["plays"][self.play()["node"]]
        self.assertEqual(len(tree["nodes"][0]["events"][-1]["data"]["text"]), ballet_stage.TEXT_LIMIT + 1)

    def test_l_historique_repris_est_regroupe_par_feature(self):
        self.log("begin")
        self.assertEqual((self.play()["session"], self.play()["legacy"]), ("shop#FEAT-001", True))

    def test_une_session_de_conductor_garde_ses_representations_et_son_mode(self):
        ballet_store.save(self.home, "session", {"item": "#3", "status": "open", "mode": "autopilot"})
        self.log("begin", conductor="#3")
        self.assertEqual((self.play()["session"], self.play()["legacy"], self.play()["mode"]), ("shop#3", False, "autopilot"))

    # --- les titres ---

    def test_le_titre_de_l_issue_arrive_en_arriere_plan_sans_son_prefixe(self):
        ballet_store.save(self.home, "rehearsal", {"id": "FEAT-001.2", "issue": "3"})
        self.log("begin")
        self.assertEqual(self.play()["title"], "FEAT-001.2")
        self.wait_for_titles()
        self.assertEqual(self.play()["title"], "Issue 3")

    def test_le_titre_n_est_demande_qu_une_fois(self):
        calls = []
        ballet_stage._read_title = lambda home, issue: calls.append(issue) or "titre"
        ballet_store.save(self.home, "rehearsal", {"id": "FEAT-001.2", "issue": "3"})
        self.log("begin")
        self.stage()
        self.wait_for_titles()
        self.stage()
        self.assertEqual(calls, ["3"])

    # --- la version ---

    def test_rien_n_a_bouge_la_page_garde_ce_qu_elle_a(self):
        self.log("begin")
        version = ballet_stage.snapshot()["version"]
        self.assertEqual(ballet_stage.snapshot(version), {"version": version, "unchanged": True})

    def test_un_evenement_change_la_version(self):
        self.log("begin")
        version = ballet_stage.snapshot()["version"]
        self.log("handoff", {"role": "dancer", "how": "start"})
        self.assertNotIn("unchanged", ballet_stage.snapshot(version))

    # --- la file et les issues proposées ---

    def test_la_file_est_celle_du_dernier_tour_du_monitor(self):
        self.set_ready([{"item": "#66", "type": "Feature", "priority": "P2", "mode": "assisted", "title": "Alerts",
                         "url": "u", "blocked_by": [{"item": "#65", "url": "v"}]}])
        ready = self.stage()["ready"]
        self.assertEqual([(item["project"], item["item"], item["blocked_by"]) for item in ready], [("shop", "#66", ["#65"])])

    def test_une_issue_publiee_proposed_attend_le_director(self):
        self.log("begin", key="move-kits", scope="workshop", conductor="move-kits")
        self.log("published", {"item": "FEAT-009", "issue": "67", "type": "Feature", "status": "proposed", "decided_alone": 4},
                 key="move-kits", scope="workshop", conductor="move-kits")
        proposed = self.stage()["proposed"]
        self.assertEqual([(item["item"], item["type"], item["decided_alone"]) for item in proposed], [("#67", "Feature", 4)])

    def test_une_issue_proposed_deja_dans_la_file_n_attend_plus(self):
        self.log("published", {"issue": "67", "status": "proposed"}, key="move-kits", scope="workshop", conductor="move-kits")
        self.set_ready([{"item": "#67"}])
        self.assertEqual(self.stage()["proposed"], [])

    def test_une_issue_publiee_ready_n_attend_pas(self):
        self.log("published", {"issue": "67", "status": "ready"}, key="move-kits", scope="workshop", conductor="move-kits")
        self.assertEqual(self.stage()["proposed"], [])

    # --- la santé, les projets ---

    def test_la_sante_dit_la_base_les_limites_et_le_monitor(self):
        self.set_ready([])
        health = self.stage()["health"]
        self.assertEqual((health["db"]["user_version"], health["limits"]["launched_today"], health["legacy_pending"]), (2, 0, False))
        self.assertEqual(health["monitor"]["seen_at"], "2026-11-22T20:00:00+00:00")
        self.assertIsNone(health["maestro"]["context_percent"])

    def test_un_projet_connu_de_la_base_seulement_est_liste(self):
        self.log("begin")
        self.assertEqual(self.stage()["projects"], [{"alias": "shop", "cast": {}, "repo": ""}])

    def test_l_url_du_repo_vient_du_remote(self):
        self.assertEqual(ballet_stage._github_url("git@github.com:o/r.git"), "https://github.com/o/r")
        self.assertEqual(ballet_stage._github_url("https://github.com/o/r"), "https://github.com/o/r")
        self.assertEqual(ballet_stage._github_url("git@gitlab.com:o/r.git"), "")

    # --- la ligne de commande, le serveur ---

    def test_seul_le_port_se_choisit(self):
        self.assertEqual(ballet_stage._parsed([]), ballet_stage.DEFAULT_PORT)
        self.assertEqual(ballet_stage._parsed(["--port", "7710"]), 7710)
        for argv in (["shop"], ["--port", "x"], ["--port"]):
            with self.assertRaises(ballet_stage.UsageError):
                ballet_stage._parsed(argv)

    def test_n_ecoute_que_la_machine(self):
        self.assertTrue(ballet_stage._is_local("127.0.0.1:7700"))
        self.assertTrue(ballet_stage._is_local("localhost:7700"))
        self.assertFalse(ballet_stage._is_local("evil.example:7700"))

    def test_les_fichiers_servis_existent(self):
        for name, _ in ballet_stage.FILES.values():
            self.assertTrue((ballet_stage.STAGE / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
