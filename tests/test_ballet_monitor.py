import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ballet_capacity  # noqa: E402
import ballet_conductors  # noqa: E402
import ballet_db  # noqa: E402
import ballet_maestro  # noqa: E402
import ballet_monitor  # noqa: E402
import ballet_program  # noqa: E402
import ballet_runtime  # noqa: E402
import ballet_store  # noqa: E402
from test_ballet_maestro import FakeOrca  # noqa: E402


def blocker(number):
    """Un bloqueur ouvert, tel que `ballet_program.ready_items` le rend."""
    return {"item": f"#{number}", "number": number, "repo": "acme/shop", "url": f"https://github.com/acme/shop/issues/{number}"}


def item(number, kind="Task", priority="High", title=None, blocked_by=(), doubt=""):
    """Un élément prêt, tel que `ballet_program.ready_items` le rend."""
    return {"item": f"#{number}", "number": number, "title": title or f"Élément {number}", "type": kind, "priority": priority,
            "mode": "", "created_at": "2026-11-01T10:00:00Z", "url": f"https://github.com/acme/shop/issues/{number}",
            "blocked_by": [blocker(found) for found in blocked_by], "launchable": not blocked_by, "doubt": doubt}


class FakeQueue:
    """La file GitHub de chaque projet, par nom de dossier : une liste d'éléments, ou une erreur à lever."""

    def __init__(self):
        self.queues = {}
        self.asked = []

    def __call__(self, home):
        self.asked.append(home.name)
        found = self.queues.get(home.name, [])
        if isinstance(found, Exception):
            raise found
        return found


class BalletMonitorTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.state = self.root / "ballet-home"
        environment = mock.patch.dict("os.environ", {"BALLET_HOME": str(self.state)})
        environment.start()
        self.addCleanup(environment.stop)
        self.orca = FakeOrca()
        self.queue = FakeQueue()
        ballet_maestro.mailbox(self.orca)
        self.register("antimurphy")

    def register(self, alias):
        folder = self.root / alias
        folder.mkdir()
        ballet_maestro.add_project(alias, str(folder))

    def turn(self):
        return ballet_monitor.once(self.orca, self.queue)

    def sent(self):
        """Les messages envoyés à la boîte : (sujet, priorité, corps), dans l'ordre."""
        rows = []
        for command in self.orca.ran("orchestration", "send"):
            value = lambda flag: command[command.index(flag) + 1]
            rows.append((value("--subject"), value("--priority"), value("--body")))
        return rows

    def subjects(self):
        return [subject for subject, _, _ in self.sent()]

    def running_conductor(self, key="antimurphy#12", terminal="term_9"):
        project, _, number = key.partition("#")
        ballet_conductors.record_launch(key, project, number, "rehearsal", terminal)

    # --- un élément passé ready ---

    # --- les dépendances : seul un élément lançable réveille Maestro ---

    def test_un_element_pret_mais_bloque_reste_muet(self):
        self.queue.queues["antimurphy"] = []
        self.turn()
        self.queue.queues["antimurphy"] = [item(2, blocked_by=[1])]
        self.assertEqual(self.turn().told, [])
        self.assertEqual(self.sent(), [])

    def test_le_premier_tour_ne_groupe_que_les_elements_lancables(self):
        self.queue.queues["antimurphy"] = [item(1), item(2, blocked_by=[1]), item(3, "Bug")]
        self.assertEqual(self.turn().told, ["antimurphy · ready (2 already)"])
        body = self.sent()[0][2]
        self.assertIn("#1 · ", body)
        self.assertIn("#3 · ", body)
        self.assertNotIn("#2 · ", body)

    def test_le_premier_tour_d_un_projet_dont_tout_est_bloque_ne_dit_rien(self):
        self.queue.queues["antimurphy"] = [item(2, blocked_by=[1])]
        self.assertEqual(self.turn().told, [])

    def test_un_element_bloque_est_signale_une_seule_fois_quand_son_dernier_bloqueur_se_ferme(self):
        self.queue.queues["antimurphy"] = [item(1), item(2, blocked_by=[1])]
        self.turn()
        self.queue.queues["antimurphy"] = [item(2)]
        self.assertEqual(self.turn().told, ["antimurphy#2 · ready"])
        self.assertEqual(self.turn().told, [])
        self.assertEqual(self.subjects()[1:], ["antimurphy#2 · ready"])

    def test_le_message_du_deblocage_dit_quel_bloqueur_s_est_ferme(self):
        self.queue.queues["antimurphy"] = [item(2, "Feature", "High", "Payer", blocked_by=[1])]
        self.turn()
        self.queue.queues["antimurphy"] = [item(2, "Feature", "High", "Payer")]
        self.turn()
        self.assertEqual(self.sent(), [("antimurphy#2 · ready", "normal",
                                        "#2 · Feature · High · Payer · https://github.com/acme/shop/issues/2\nunblocked: #1 closed")])

    def test_un_element_encore_bloque_par_un_autre_bloqueur_reste_muet(self):
        self.queue.queues["antimurphy"] = [item(3, blocked_by=[1, 2])]
        self.turn()
        self.queue.queues["antimurphy"] = [item(3, blocked_by=[2])]
        self.assertEqual(self.turn().told, [])
        self.queue.queues["antimurphy"] = [item(3)]
        self.assertEqual(self.turn().told, ["antimurphy#3 · ready"])
        self.assertTrue(self.sent()[0][2].endswith("unblocked: #2 closed"))

    def test_plusieurs_bloqueurs_fermes_d_un_coup_sont_tous_nommes(self):
        self.queue.queues["antimurphy"] = [item(3, blocked_by=[1, 2])]
        self.turn()
        self.queue.queues["antimurphy"] = [item(3)]
        self.turn()
        self.assertTrue(self.sent()[0][2].endswith("unblocked: #1, #2 closed"))

    def test_un_element_qui_se_rebloque_puis_se_debloque_est_signale_de_nouveau(self):
        self.queue.queues["antimurphy"] = [item(2)]
        self.turn()
        self.queue.queues["antimurphy"] = [item(2, blocked_by=[1])]
        self.assertEqual(self.turn().told, [])
        self.queue.queues["antimurphy"] = [item(2)]
        self.assertEqual(self.turn().told, ["antimurphy#2 · ready"])

    def test_un_element_deja_lancable_n_est_pas_resignale_quand_un_bloqueur_s_ajoute_puis_reste(self):
        self.queue.queues["antimurphy"] = [item(2)]
        self.turn()
        self.queue.queues["antimurphy"] = [item(2, blocked_by=[1])]
        self.turn()
        self.assertEqual(self.turn().told, [])

    def test_un_doute_de_dependance_reveille_maestro_et_le_dit(self):
        self.queue.queues["antimurphy"] = []
        self.turn()
        self.queue.queues["antimurphy"] = [item(2, doubt="dependency cycle: #2 → #3 → #2", blocked_by=[3])]
        self.assertEqual(self.turn().told, ["antimurphy#2 · ready"])
        self.assertTrue(self.sent()[0][2].endswith("\ndependency: dependency cycle: #2 → #3 → #2"))
        self.assertEqual(self.turn().told, [])

    def test_un_bloqueur_ferme_not_planned_signale_l_element_avec_le_doute(self):
        self.queue.queues["antimurphy"] = [item(2, blocked_by=[1])]
        self.turn()
        self.queue.queues["antimurphy"] = [item(2, doubt="blocker #1 was closed as not planned, not delivered")]
        self.assertEqual(self.turn().told, ["antimurphy#2 · ready"])
        self.assertIn("dependency: blocker #1 was closed as not planned", self.sent()[0][2])
        self.assertNotIn("unblocked", self.sent()[0][2])

    def test_les_elements_bloques_sont_retenus_pour_ready_avec_leurs_bloqueurs(self):
        self.queue.queues["antimurphy"] = [item(1), item(2, blocked_by=[1])]
        self.turn()
        kept = ballet_monitor.read_ready()["antimurphy"]
        self.assertEqual([found["item"] for found in kept], ["#1", "#2"])
        self.assertEqual([found["item"] for found in kept[1]["blocked_by"]], ["#1"])

    def test_la_decision_sous_le_message_du_deblocage_est_celle_de_la_regle(self):
        self.queue.queues["antimurphy"] = [item(2, blocked_by=[1])]
        self.turn()
        self.queue.queues["antimurphy"] = [item(2)]
        self.turn()
        config = ballet_maestro.read_config()
        config["projects"]["antimurphy"]["auto_launch"] = ["Task"]
        ballet_maestro.write_config(config)
        message = {"type": "status", "subject": "antimurphy#2 · ready", "body": self.sent()[0][2]}
        self.assertEqual(ballet_maestro._body_with_decisions(message, config, None).splitlines()[1:],
                         ["DECISION: launch", "unblocked: #1 closed"])

    def test_un_element_nouvellement_pret_est_signale_une_seule_fois(self):
        self.queue.queues["antimurphy"] = []
        self.turn()
        self.queue.queues["antimurphy"] = [item(12)]
        self.assertEqual(self.turn().told, ["antimurphy#12 · ready"])
        self.assertEqual(self.turn().told, [])
        self.assertEqual(self.subjects(), ["antimurphy#12 · ready"])

    def test_un_element_qui_quitte_ready_puis_y_revient_est_signale_de_nouveau(self):
        self.queue.queues["antimurphy"] = [item(12)]
        self.turn()
        self.queue.queues["antimurphy"] = []
        self.turn()
        self.queue.queues["antimurphy"] = [item(12)]
        self.assertEqual(self.turn().told, ["antimurphy#12 · ready"])

    def test_seul_le_nouvel_element_est_signale_quand_un_autre_reste_pret(self):
        self.queue.queues["antimurphy"] = [item(12)]
        self.turn()
        self.queue.queues["antimurphy"] = [item(12), item(13, "Bug")]
        self.assertEqual(self.turn().told, ["antimurphy#13 · ready"])

    def test_le_message_dit_le_type_le_titre_la_priorite_et_le_lien(self):
        self.queue.queues["antimurphy"] = []
        self.turn()
        self.queue.queues["antimurphy"] = [item(12, "Bug", "Urgent", "Le panier se vide")]
        self.turn()
        self.assertEqual(self.sent(), [("antimurphy#12 · ready", "normal",
                                        "#12 · Bug · Urgent · Le panier se vide · https://github.com/acme/shop/issues/12")])
        self.assertEqual(self.orca.ran("orchestration", "send")[0][2:6], ["--to", "run:run_1", "--type", "status"])

    def test_sans_priorite_le_message_le_dit(self):
        self.queue.queues["antimurphy"] = []
        self.turn()
        self.queue.queues["antimurphy"] = [item(3, priority="")]
        self.turn()
        self.assertIn("#3 · Task · no priority · ", self.sent()[0][2])

    def test_au_premier_tour_d_un_projet_les_elements_deja_prets_sont_groupes_en_un_message(self):
        self.queue.queues["antimurphy"] = [item(5, "Bug", "Urgent"), item(3), item(9, "Feature", "")]
        report = self.turn()
        self.assertEqual(report.told, ["antimurphy · ready (3 already)"])
        subject, priority, body = self.sent()[0]
        self.assertEqual((subject, priority), ("antimurphy · ready (3 already)", "normal"))
        self.assertEqual([line.split(" · ")[0] for line in body.splitlines()], ["#5", "#3", "#9"])
        self.assertEqual(len(self.sent()), 1)

    def test_le_premier_tour_se_groupe_par_projet(self):
        self.register("beta")
        self.queue.queues["antimurphy"] = [item(1), item(2)]
        self.queue.queues["beta"] = [item(7)]
        self.turn()
        self.assertEqual(self.subjects(), ["antimurphy · ready (2 already)", "beta · ready (1 already)"])

    def test_le_premier_tour_d_un_projet_arrive_apres_les_autres(self):
        self.queue.queues["antimurphy"] = [item(1)]
        self.turn()
        self.register("beta")
        self.queue.queues["beta"] = [item(7), item(8)]
        self.assertEqual(self.turn().told, ["beta · ready (2 already)"])

    def test_un_premier_tour_sans_element_ne_dit_rien_et_le_projet_est_vu(self):
        self.assertEqual(self.turn().told, [])
        self.assertEqual(ballet_monitor.read_ready(), {"antimurphy": []})
        self.queue.queues["antimurphy"] = [item(4)]
        self.assertEqual(self.turn().told, ["antimurphy#4 · ready"])

    def test_les_transitions_vues_survivent_a_un_redemarrage_du_monitor(self):
        self.queue.queues["antimurphy"] = [item(12)]
        self.turn()
        self.assertEqual(ballet_monitor.read_ready()["antimurphy"][0]["number"], 12)
        self.assertEqual(self.turn().told, [])

    def test_la_file_vue_vit_dans_la_base_sans_fichier_a_cote(self):
        self.queue.queues["antimurphy"] = [item(12)]
        self.turn()
        self.assertFalse((self.state / "monitor.json").exists())
        self.assertFalse((self.state / "monitor.lock").exists())

    def test_les_elements_retenus_gardent_l_ordre_de_la_file(self):
        self.queue.queues["antimurphy"] = [item(9), item(2), item(5)]
        self.turn()
        self.assertEqual([found["number"] for found in ballet_monitor.read_ready()["antimurphy"]], [9, 2, 5])

    def test_un_envoi_qui_echoue_n_est_pas_note_et_le_tour_suivant_le_refait(self):
        self.queue.queues["antimurphy"] = []
        self.turn()
        self.queue.queues["antimurphy"] = [item(12)]
        self.orca.send_failures = 1
        report = self.turn()
        self.assertEqual((report.told, len(report.errors)), ([], 1))
        self.assertEqual(self.turn().told, ["antimurphy#12 · ready"])

    def test_un_premier_tour_dont_l_envoi_echoue_reste_un_premier_tour(self):
        self.queue.queues["antimurphy"] = [item(1), item(2)]
        self.orca.send_failures = 1
        self.turn()
        self.assertEqual(self.turn().told, ["antimurphy · ready (2 already)"])

    def test_une_file_illisible_est_une_erreur_du_projet_et_les_autres_continuent(self):
        self.register("beta")
        self.queue.queues["antimurphy"] = ballet_program.ProgramError("gh did not answer")
        self.queue.queues["beta"] = [item(7)]
        report = self.turn()
        self.assertEqual(report.errors, ["antimurphy: gh did not answer"])
        self.assertEqual(report.told, ["beta · ready (1 already)"])
        self.assertNotIn("antimurphy", ballet_monitor.read_ready())

    def test_une_file_illisible_ne_vide_pas_ce_qui_etait_connu(self):
        self.queue.queues["antimurphy"] = [item(12)]
        self.turn()
        self.queue.queues["antimurphy"] = ballet_program.ProgramError("rate limited")
        self.turn()
        self.queue.queues["antimurphy"] = [item(12)]
        self.assertEqual(self.turn().told, [])

    def test_sans_boite_le_monitor_le_dit_et_ne_note_rien(self):
        (self.state / "maestro.toml").unlink()
        ballet_runtime.update(mailbox_terminal="", mailbox_run="")
        self.register("antimurphy2")
        self.queue.queues["antimurphy2"] = [item(1)]
        report = self.turn()
        self.assertIn("no mailbox yet", report.errors[0])
        self.assertEqual(ballet_monitor.read_ready(), {})

    def test_le_monitor_ne_lance_jamais_rien(self):
        self.queue.queues["antimurphy"] = [item(12)]
        self.running_conductor("antimurphy#99", "term_gone")
        creates = len(self.orca.ran("terminal", "create"))
        self.turn()
        self.turn()
        self.assertEqual(len(self.orca.ran("terminal", "create")), creates)
        self.assertEqual(self.orca.ran("terminal", "send"), [])

    # --- un Conductor disparu ---

    def test_un_conductor_dont_le_terminal_a_disparu_est_signale_en_haute_priorite_et_sa_ligne_marquee(self):
        self.running_conductor()
        report = self.turn()
        self.assertEqual(report.told, ["antimurphy#12 · gone"])
        subject, priority, body = self.sent()[0]
        self.assertEqual((subject, priority), ("antimurphy#12 · gone", "high"))
        line = ballet_conductors.read()["antimurphy#12"]
        self.assertEqual(body, f"The Conductor of antimurphy#12 is gone: its terminal term_9 no longer exists in Orca "
                               f"(rehearsal, started {line['started']}, last event none).")
        self.assertEqual((line["state"], ballet_conductors.state_of(line)), ("gone", "gone"))
        self.assertNotEqual(ballet_conductors.state_of(line), ballet_conductors.RUNNING)

    # --- un Conductor fini resté ouvert ---

    def finished_conductor(self, minutes_ago=30, key="antimurphy#12", terminal="term_9", kind="rehearsal"):
        """Un Conductor lancé (par Maestro si `kind`), fini il y a `minutes_ago` minutes, son terminal encore vivant."""
        from datetime import datetime, timedelta, timezone
        if kind:
            ballet_conductors.record_launch(key, "antimurphy", key.split("#")[1], kind, terminal)
        ballet_conductors.note_events([{"type": "status", "from": terminal, "subject": f"{key} · done"}])
        when = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")
        with ballet_db.writing() as connection:   # le `done` date de `minutes_ago`
            connection.execute("UPDATE events SET at = ? WHERE id = (SELECT max(id) FROM events WHERE node = "
                               "(SELECT node FROM conductors WHERE id = ?))", (when, key))
        self.orca.terminals.append(terminal)

    def close_after(self, minutes):
        config = ballet_maestro.read_config()
        config["conductors"] = {"close_finished_after_minutes": minutes}
        ballet_maestro.write_config(config)

    def test_un_conductor_fini_reste_ouvert_au_dela_du_delai_est_signale_une_fois(self):
        self.finished_conductor(minutes_ago=30)
        self.assertEqual(self.turn().told, ["antimurphy#12 · finished"])
        subject, priority, body = self.sent()[-1]
        self.assertEqual(body, f"The rehearsal Conductor of antimurphy#12 finished at {ballet_conductors.read()['antimurphy#12']['seen']} "
                               "and its terminal term_9 is still open after 10 min.")
        self.assertEqual(self.turn().told, [])
        self.assertTrue(ballet_conductors.read()["antimurphy#12"]["finished_told"])

    def test_un_conductor_fini_avant_le_delai_n_est_pas_signale(self):
        self.finished_conductor(minutes_ago=3)
        self.assertEqual(self.turn().told, [])

    def test_le_delai_vient_de_la_config(self):
        self.finished_conductor(minutes_ago=3)
        self.close_after(2)
        self.assertEqual(self.turn().told, ["antimurphy#12 · finished"])

    def test_un_delai_de_zero_ne_signale_jamais(self):
        self.finished_conductor(minutes_ago=600)
        self.close_after(0)
        self.assertEqual(self.turn().told, [])

    def test_un_delai_invalide_est_une_erreur_du_tour_qui_n_arrete_pas_le_reste(self):
        self.finished_conductor(minutes_ago=30)
        self.running_conductor("antimurphy#13", "term_7")
        self.close_after("soon")
        report = self.turn()
        self.assertEqual(report.told, ["antimurphy#13 · gone"])
        self.assertIn("close_finished_after_minutes", report.errors[0])

    def test_un_conductor_que_maestro_n_a_pas_lance_n_est_pas_signale(self):
        self.finished_conductor(minutes_ago=30, kind="")
        self.assertEqual(self.turn().told, [])

    def test_un_conductor_fini_dont_le_terminal_est_ferme_n_est_pas_signale(self):
        self.finished_conductor(minutes_ago=30)
        self.orca.terminals.remove("term_9")
        self.assertEqual(self.turn().told, [])

    def test_un_conductor_disparu_n_est_signale_qu_une_fois(self):
        self.running_conductor()
        self.turn()
        self.assertEqual(self.turn().told, [])
        self.assertEqual(self.subjects().count("antimurphy#12 · gone"), 1)

    def test_un_conductor_dont_le_terminal_vit_n_est_pas_signale(self):
        self.running_conductor()
        self.orca.terminals.append("term_9")
        self.assertEqual(self.turn().told, [])
        self.assertEqual(ballet_conductors.state_of(ballet_conductors.read()["antimurphy#12"]), ballet_conductors.RUNNING)

    def test_un_conductor_fini_n_est_pas_signale_meme_terminal_ferme(self):
        self.running_conductor()
        ballet_conductors.note_events([{"type": "status", "from": "term_9", "subject": "antimurphy#12 · done"}])
        self.assertEqual(self.turn().told, [])

    def test_orca_injoignable_ne_marque_aucun_conductor(self):
        self.running_conductor()
        self.orca.unreachable = True
        report = self.turn()
        self.assertEqual(len(report.errors), 1)
        self.assertEqual(ballet_conductors.state_of(ballet_conductors.read()["antimurphy#12"]), ballet_conductors.RUNNING)

    def test_un_gone_dont_l_envoi_echoue_n_est_pas_marque_et_revient_au_tour_suivant(self):
        self.running_conductor()
        self.orca.send_failures = 1
        self.turn()
        self.assertEqual(ballet_conductors.state_of(ballet_conductors.read()["antimurphy#12"]), ballet_conductors.RUNNING)
        self.assertEqual(self.turn().told, ["antimurphy#12 · gone"])

    def test_chaque_conductor_disparu_a_son_message(self):
        self.running_conductor("antimurphy#12", "term_8")
        self.running_conductor("antimurphy#FEAT-002", "term_9")
        self.assertEqual(sorted(self.turn().told), ["antimurphy#12 · gone", "antimurphy#FEAT-002 · gone"])

    def test_sans_conductor_en_cours_orca_n_est_pas_interroge_pour_les_terminaux(self):
        self.turn()
        self.assertEqual(self.orca.ran("terminal", "list"), [])

    def test_un_conductor_relance_apres_sa_disparition_est_de_nouveau_surveille(self):
        self.running_conductor()
        self.turn()
        self.running_conductor(terminal="term_10")
        self.assertEqual(self.turn().told, ["antimurphy#12 · gone"])

    # --- un Conductor qui n'écrit plus ---

    def play(self, minutes_ago=0, scope="rehearsal", key="antimurphy#12", name="FEAT-001.1"):
        """Un Conductor `running` qui joue une Rehearsal (ou un Workshop) ouverte depuis `minutes_ago` : le tour du Dancer commence."""
        self.running_conductor(key)
        self.orca.terminals.append("term_9")
        self.at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
        self.item = "#" + key.partition("#")[2]
        self.log(scope, name, "begin", {"item": "#12"})
        self.log(scope, name, "handoff", {"role": "dancer", "how": "start", "text": "go"})

    def log(self, scope, name, event, detail=None, minutes_ago=None):
        when = self.at if minutes_ago is None else datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
        with ballet_db.writing() as connection:
            ballet_store.log_in(connection, "antimurphy", scope, name, event, detail or {}, conductor=self.item,
                                at=when.isoformat(timespec="seconds"))

    def age(self, minutes):
        """Tout le journal vieillit de `minutes` : le temps passe sans rien écrire."""
        with ballet_db.writing() as connection:
            for row in connection.execute("SELECT id, at FROM events").fetchall():
                older = datetime.fromisoformat(row["at"]) - timedelta(minutes=minutes)
                connection.execute("UPDATE events SET at = ? WHERE id = ?", (older.isoformat(timespec="seconds"), row["id"]))

    def idle_marks(self):
        with ballet_db.reading() as connection:
            return [json.loads(row["data"]) for row in connection.execute("SELECT data FROM events WHERE kind = 'idle' ORDER BY id")]

    def idle_after(self, minutes):
        config = ballet_maestro.read_config()
        config["conductors"] = {"idle_after_minutes": minutes}
        ballet_maestro.write_config(config)

    def worktree_committed(self, minutes_ago, name="FEAT-001.1"):
        """Le worktree de la Rehearsal, un vrai dépôt git dont le dernier commit date de `minutes_ago`."""
        worktree = Path(self._tmp.name) / f"worktree-{name}"
        worktree.mkdir()
        when = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")
        environment = {**os.environ, "GIT_COMMITTER_DATE": when, "GIT_AUTHOR_DATE": when, "GIT_AUTHOR_NAME": "t",
                       "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        for command in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "task"]):
            subprocess.run(["git", "-C", str(worktree), *command], check=True, env=environment)
        with ballet_db.writing() as connection:
            ballet_store.save_in(connection, "antimurphy", "rehearsal", {"id": name, "status": "open", "worktree": str(worktree)})

    def test_un_commit_recent_dans_le_worktree_est_un_signe_de_vie(self):
        self.play(minutes_ago=40)
        self.worktree_committed(minutes_ago=5)
        self.assertEqual(self.turn().told, [])

    def test_un_commit_ancien_n_empeche_pas_l_avis(self):
        self.play(minutes_ago=40)
        self.worktree_committed(minutes_ago=30)
        self.assertEqual(self.turn().told, ["antimurphy#12 · idle"])
        self.assertIn("no event nor commit for 30 min", self.sent()[0][2])

    def test_un_commit_apres_l_avis_1_rearme_l_episode(self):
        self.play(minutes_ago=40)
        self.turn()
        self.worktree_committed(minutes_ago=1)
        self.assertEqual(self.turn().told, [])

    def test_un_worktree_disparu_ne_compte_pas(self):
        self.play(minutes_ago=25)
        with ballet_db.writing() as connection:
            ballet_store.save_in(connection, "antimurphy", "rehearsal", {"id": "FEAT-001.1", "status": "open", "worktree": "/nowhere"})
        self.assertEqual(self.turn().told, ["antimurphy#12 · idle"])

    def test_pas_d_avis_avant_le_seuil(self):
        self.play(minutes_ago=19)
        self.assertEqual(self.turn().told, [])
        self.assertEqual(self.idle_marks(), [])

    def test_l_avis_1_dit_les_faits_en_normal_et_laisse_une_marque_au_journal(self):
        self.play(minutes_ago=25)
        self.assertEqual(self.turn().told, ["antimurphy#12 · idle"])
        subject, priority, body = self.sent()[0]
        self.assertEqual((subject, priority), ("antimurphy#12 · idle", "normal"))
        self.assertRegex(body, r"^Rehearsal FEAT-001\.1 · idle notice 1 of 2 · no event nor commit for 25 min since \S+ "
                               r"· waiting on the dancer \(turn started \S+\)$")
        self.assertEqual(self.idle_marks(), [{"notice": 1, "silent_minutes": 25, "since": self.at.isoformat(timespec="seconds"),
                                              "role": "dancer"}])

    def test_le_corps_ne_donne_aucune_instruction(self):
        self.play(minutes_ago=25)
        self.turn()
        for word in ("nudge", "remind", "stop", "ask"):
            self.assertNotIn(word, self.sent()[0][2].casefold())

    def test_pas_de_doublon_au_tour_suivant(self):
        self.play(minutes_ago=25)
        self.turn()
        self.assertEqual(self.turn().told, [])
        self.assertEqual(len(self.idle_marks()), 1)

    def test_l_avis_2_vient_un_intervalle_apres_l_avis_1_en_haute_priorite(self):
        self.play(minutes_ago=25)
        self.turn()
        self.age(10)
        self.assertEqual(self.turn().told, [])
        self.age(11)
        self.assertEqual(self.turn().told, ["antimurphy#12 · idle"])
        subject, priority, body = self.sent()[1]
        self.assertEqual(priority, "high")
        self.assertIn("idle notice 2 of 2 · no event nor commit for 46 min", body)

    def test_jamais_plus_de_deux_avis_par_episode(self):
        self.play(minutes_ago=25)
        self.turn()
        self.age(21)
        self.turn()
        self.age(60)
        self.assertEqual(self.turn().told, [])
        self.assertEqual([mark["notice"] for mark in self.idle_marks()], [1, 2])

    def test_une_preuve_ouverte_n_est_pas_un_silence(self):
        self.play(minutes_ago=25)
        self.log("rehearsal", "FEAT-001.1", "proof-start", {"command": "make test"}, minutes_ago=24)
        self.assertEqual(self.turn().told, [])

    def test_une_mutation_ouverte_n_est_pas_un_silence(self):
        self.play(minutes_ago=25)
        self.log("rehearsal", "FEAT-001.1", "mutation-start", {"tool": "mutmut"}, minutes_ago=24)
        self.assertEqual(self.turn().told, [])

    def test_l_attente_du_director_n_est_pas_un_silence(self):
        self.play(minutes_ago=25)
        self.log("rehearsal", "FEAT-001.1", "escalate", {"reason": "Which name?"}, minutes_ago=24)
        self.assertEqual(self.turn().told, [])

    def test_la_preuve_finie_le_silence_compte_de_nouveau(self):
        self.play(minutes_ago=60)
        self.log("rehearsal", "FEAT-001.1", "proof-start", {"command": "make test"}, minutes_ago=59)
        self.log("rehearsal", "FEAT-001.1", "proof-end", {"passed": True}, minutes_ago=30)
        self.assertEqual(self.turn().told, ["antimurphy#12 · idle"])
        self.assertIn("no event nor commit for 30 min", self.sent()[0][2])

    def test_une_nouvelle_activite_rearme_l_episode(self):
        self.play(minutes_ago=25)
        self.turn()
        self.age(5)
        self.log("rehearsal", "FEAT-001.1", "message", {"from": "dancer", "type": "question", "to": "choreographer"}, minutes_ago=0)
        self.assertEqual(self.turn().told, [])
        self.age(25)
        self.assertEqual(self.turn().told, ["antimurphy#12 · idle"])
        self.assertIn("idle notice 1 of 2", self.sent()[1][2])
        self.assertEqual([mark["notice"] for mark in self.idle_marks()], [1, 1])

    def test_une_relance_n_est_pas_de_l_activite(self):
        self.play(minutes_ago=25)
        self.turn()
        self.age(21)
        self.log("rehearsal", "FEAT-001.1", "handoff", {"role": "dancer", "how": "nudge", "text": "hurry"}, minutes_ago=1)
        self.log("rehearsal", "FEAT-001.1", "nudge", {"role": "dancer"}, minutes_ago=1)
        self.assertEqual(self.turn().told, ["antimurphy#12 · idle"])
        self.assertIn("idle notice 2 of 2 · no event nor commit for 46 min", self.sent()[1][2])

    def test_l_activite_d_un_enfant_compte(self):
        self.play(minutes_ago=60)
        self.log("rehearsal", "FEAT-001.1", "message", {"from": "dancer", "type": "question", "to": "choreographer"}, minutes_ago=5)
        self.assertEqual(self.turn().told, [])

    def test_un_seuil_de_zero_ne_dit_jamais_rien(self):
        self.play(minutes_ago=600)
        self.idle_after(0)
        self.assertEqual(self.turn().told, [])

    def test_le_seuil_vient_de_la_config(self):
        self.play(minutes_ago=5)
        self.idle_after(3)
        self.assertEqual(self.turn().told, ["antimurphy#12 · idle"])

    def test_un_seuil_invalide_est_une_erreur_du_tour_qui_n_arrete_pas_le_reste(self):
        self.play(minutes_ago=25)
        self.idle_after(-2)
        report = self.turn()
        self.assertEqual(report.told, [])
        self.assertIn("idle_after_minutes", report.errors[0])

    def test_sans_tour_ouvert_le_corps_dit_qu_aucun_worker_n_est_attendu(self):
        self.play(minutes_ago=25)
        self.log("rehearsal", "FEAT-001.1", "message", {"from": "dancer", "type": "report"}, minutes_ago=24)
        self.turn()
        self.assertTrue(self.sent()[0][2].endswith("waiting on no worker"))

    def test_le_role_attendu_est_celui_du_tour_ouvert_le_plus_recent(self):
        self.play(minutes_ago=40)
        self.log("rehearsal", "FEAT-001.1", "message", {"from": "dancer", "type": "report"}, minutes_ago=30)
        self.log("rehearsal", "FEAT-001.1", "handoff", {"role": "critic", "how": "start", "text": "review"}, minutes_ago=29)
        self.turn()
        self.assertRegex(self.sent()[0][2], r"waiting on the critic \(turn started ")

    def test_un_workshop_idle_est_signale_comme_tel(self):
        self.play(minutes_ago=25, scope="workshop", name="OPP-75")
        self.turn()
        self.assertTrue(self.sent()[0][2].startswith("Workshop OPP-75 · idle notice 1 of 2"))

    def test_un_conductor_qui_ne_tourne_plus_n_est_pas_surveille(self):
        self.play(minutes_ago=25)
        ballet_conductors.note_events([{"type": "status", "from": "term_9", "subject": "antimurphy#12 · done"}])
        self.assertEqual(self.turn().told, [])

    def test_un_conductor_sans_jeu_ouvert_n_est_pas_signale(self):
        self.running_conductor()
        self.orca.terminals.append("term_9")
        self.assertEqual(self.turn().told, [])

    def test_un_envoi_qui_echoue_n_est_pas_note_et_revient_au_tour_suivant(self):
        self.play(minutes_ago=25)
        self.orca.send_failures = 1
        self.assertEqual(len(self.turn().errors), 1)
        self.assertEqual(self.idle_marks(), [])
        self.assertEqual(self.turn().told, ["antimurphy#12 · idle"])

    def test_chaque_conductor_idle_a_son_avis(self):
        self.play(minutes_ago=25)
        self.play(minutes_ago=25, scope="workshop", key="antimurphy#OPP-9", name="OPP-9")
        self.assertEqual(sorted(self.turn().told), ["antimurphy#12 · idle", "antimurphy#OPP-9 · idle"])

    # --- le contexte de Maestro ---

    def maestro_session(self, session="s-1", tokens=312_000):
        """Une session Maestro qui tient le bail sous cet id, et son transcript dans un dossier Claude jetable."""
        claude = self.root / "claude"
        environment = mock.patch.dict("os.environ", {"CLAUDE_CONFIG_DIR": str(claude), "CLAUDE_CODE_SESSION_ID": session})
        environment.start()
        self.addCleanup(environment.stop)
        ballet_maestro.claim(take_over=True)
        self.write_transcript(session, tokens)

    def write_transcript(self, session, tokens):
        path = self.root / "claude" / "projects" / "-Users-me-ballet" / f"{session}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        usage = {"input_tokens": 2, "cache_read_input_tokens": tokens - 2, "cache_creation_input_tokens": 0, "output_tokens": 9}
        path.write_text(json.dumps({"type": "assistant", "message": {"model": "claude-opus-5-5", "usage": usage}}) + "\n", encoding="utf-8")

    def set_maestro(self, **settings):
        config = ballet_maestro.read_config()
        config["maestro"] = {**config.get("maestro", {}), **settings}
        ballet_maestro.write_config(config)

    def context_events(self):
        return [row for row in self.sent() if row[0] == "maestro · context over threshold"]

    def test_un_contexte_au_dessus_du_seuil_est_signale_a_maestro_avec_les_faits(self):
        self.maestro_session("s-1", tokens=312_000)
        self.assertEqual(self.turn().told, ["maestro · context over threshold"])
        subject, priority, body = self.context_events()[0]
        self.assertEqual(priority, "normal")
        self.assertEqual(body, "Maestro's context is 312000 tokens · 31% of 1000000 · threshold 30% · session s-1")

    def test_l_evenement_ne_donne_aucune_instruction(self):
        self.maestro_session("s-1", tokens=312_000)
        self.turn()
        body = self.context_events()[0][2].lower()
        for word in ("restart", "should", "must", "decision", "ballet_restart"):
            self.assertNotIn(word, body)

    def test_un_contexte_sous_le_seuil_ne_dit_rien(self):
        self.maestro_session("s-1", tokens=290_000)
        self.assertEqual(self.turn().told, [])

    def test_un_contexte_pile_au_seuil_est_signale(self):
        self.maestro_session("s-1", tokens=300_000)
        self.assertEqual(self.turn().told, ["maestro · context over threshold"])

    def test_un_seuil_de_zero_ne_signale_jamais(self):
        self.maestro_session("s-1", tokens=900_000)
        self.set_maestro(restart_at_context_percent=0)
        self.assertEqual(self.turn().told, [])

    def test_le_seuil_et_la_fenetre_viennent_de_la_config(self):
        self.maestro_session("s-1", tokens=150_000)
        self.assertEqual(self.turn().told, [])
        self.set_maestro(restart_at_context_percent=20, context_window_tokens=500_000)
        self.assertEqual(self.turn().told, ["maestro · context over threshold"])
        self.assertEqual(self.context_events()[0][2], "Maestro's context is 150000 tokens · 30% of 500000 · threshold 20% · session s-1")

    def test_le_depassement_n_est_signale_qu_une_fois_par_session(self):
        self.maestro_session("s-1", tokens=312_000)
        self.turn()
        self.assertEqual(self.turn().told, [])
        self.write_transcript("s-1", 100_000)   # une compaction : le contexte retombe
        self.assertEqual(self.turn().told, [])
        self.write_transcript("s-1", 400_000)   # puis repasse au-dessus : la même session ne redemande rien
        self.assertEqual(self.turn().told, [])
        self.assertEqual(len(self.context_events()), 1)

    def test_apres_un_redemarrage_la_nouvelle_session_est_de_nouveau_surveillee(self):
        self.maestro_session("s-1", tokens=312_000)
        self.turn()
        ballet_maestro.release_lease()
        self.assertEqual(self.turn().told, [])
        self.maestro_session("s-2", tokens=45_000)
        self.assertEqual(self.turn().told, [])
        self.write_transcript("s-2", 320_000)
        self.assertEqual(self.turn().told, ["maestro · context over threshold"])
        self.assertIn("session s-2", self.context_events()[1][2])

    def test_un_envoi_qui_echoue_n_est_pas_note_et_revient_au_tour_suivant(self):
        self.maestro_session("s-1", tokens=312_000)
        self.orca.send_failures = 1
        self.assertEqual(self.turn().told, [])
        self.assertEqual(self.turn().told, ["maestro · context over threshold"])

    def test_sans_session_maestro_le_monitor_ne_lit_rien(self):
        self.assertEqual(self.turn().errors, [])
        ballet_maestro.release_lease()
        self.assertEqual(self.turn().told, [])

    def test_un_bail_sans_id_de_session_est_une_erreur_du_tour_qui_n_arrete_pas_le_reste(self):
        with mock.patch.dict("os.environ", clear=False) as environment:
            environment.pop("CLAUDE_CODE_SESSION_ID", None)
            ballet_maestro.claim(take_over=True)
        self.running_conductor("antimurphy#13", "term_7")
        report = self.turn()
        self.assertEqual(report.told, ["antimurphy#13 · gone"])
        self.assertIn("no Claude session id", report.errors[0])

    def test_un_transcript_introuvable_est_une_erreur_du_tour(self):
        self.maestro_session("s-1")
        (self.root / "claude" / "projects" / "-Users-me-ballet" / "s-1.jsonl").unlink()
        report = self.turn()
        self.assertEqual(report.told, [])
        self.assertIn("no transcript for session s-1", report.errors[0])

    def test_un_transcript_sans_message_ne_dit_rien(self):
        self.maestro_session("s-1")
        (self.root / "claude" / "projects" / "-Users-me-ballet" / "s-1.jsonl").write_text("", encoding="utf-8")
        report = self.turn()
        self.assertEqual((report.told, report.errors), ([], []))

    def test_un_contexte_plus_grand_que_la_fenetre_est_une_erreur_pas_un_evenement(self):
        self.maestro_session("s-1", tokens=1_200_000)
        report = self.turn()
        self.assertEqual(report.told, [])
        self.assertIn("context_window_tokens", report.errors[0])

    def test_un_seuil_invalide_est_une_erreur_du_tour_qui_n_arrete_pas_le_reste(self):
        self.maestro_session("s-1", tokens=900_000)
        self.set_maestro(restart_at_context_percent="soon")
        self.running_conductor("antimurphy#13", "term_7")
        report = self.turn()
        self.assertEqual(report.told, ["antimurphy#13 · gone"])
        self.assertIn("restart_at_context_percent", report.errors[0])

    def test_la_file_et_le_contexte_gardent_chacun_leur_part_de_l_etat(self):
        self.maestro_session("s-1", tokens=312_000)
        self.queue.queues["antimurphy"] = [item(12)]
        self.turn()
        self.assertEqual([found["number"] for found in ballet_monitor.read_ready()["antimurphy"]], [12])
        self.queue.queues["antimurphy"] = [item(12), item(13)]
        self.assertEqual(self.turn().told, ["antimurphy#13 · ready"])   # le contexte n'est pas redit
        self.assertEqual(len(self.context_events()), 1)

    def test_le_monitor_lit_le_transcript_sans_rien_ecrire_dans_le_dossier_de_claude(self):
        self.maestro_session("s-1", tokens=312_000)
        before = sorted(path.name for path in (self.root / "claude").rglob("*"))
        self.turn()
        self.assertEqual(sorted(path.name for path in (self.root / "claude").rglob("*")), before)

    # --- la capacité de Claude (OPP-88) ---

    def capture(self, five_hour=None, seven_day=None, minutes_ago=0):
        """Ce que la statusline de Claude a noté, il y a `minutes_ago` minutes (une fenêtre à None : absente)."""
        reset = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(microsecond=0).isoformat()
        windows = {name: {"used_percent": used, "resets_at": reset}
                   for name, used in (("five_hour", five_hour), ("seven_day", seven_day)) if used is not None}
        ballet_capacity.record("claude", windows, now=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago))
        return reset

    def set_capacity(self, **settings):
        config = ballet_maestro.read_config()
        config["capacity"] = {**config.get("capacity", {}), **settings}
        ballet_maestro.write_config(config)

    def capacity_events(self):
        return [row for row in self.sent() if row[0].startswith("capacity · ")]

    def test_la_fenetre_de_5_h_qui_passe_le_seuil_est_signalee_avec_les_faits(self):
        reset = self.capture(five_hour=93.5)
        self.assertEqual(self.turn().told, ["capacity · five_hour · above threshold"])
        subject, priority, body = self.capacity_events()[0]
        self.assertEqual(priority, "normal")
        self.assertEqual(body, f"five_hour window is 94% used · threshold 90% · resets at {reset}")

    def test_l_evenement_ne_donne_aucune_instruction(self):
        self.capture(five_hour=93)
        self.turn()
        self.capture(five_hour=70)
        self.turn()
        for _, _, body in self.capacity_events():
            for word in ("standby", "launch", "should", "must", "decision", "wait", "ask"):
                self.assertNotIn(word, body.lower())

    def test_un_pourcentage_pile_au_seuil_est_signale(self):
        self.capture(five_hour=90)
        self.assertEqual(self.turn().told, ["capacity · five_hour · above threshold"])

    def test_sous_le_seuil_le_monitor_ne_dit_rien(self):
        self.capture(five_hour=89.9, seven_day=10)
        self.assertEqual(self.turn().told, [])
        self.assertEqual(ballet_monitor.read_capacity_alerts(), {})

    def test_le_franchissement_n_est_signale_qu_une_fois(self):
        self.capture(five_hour=93)
        self.turn()
        self.capture(five_hour=97)
        self.assertEqual(self.turn().told, [])
        self.assertEqual(len(self.capacity_events()), 1)

    def test_la_redescente_est_signalee_une_fois_la_marge_passee(self):
        self.capture(five_hour=93)
        self.turn()
        self.capture(five_hour=85)   # sous le seuil, mais pas de 5 points : le chiffre peut remonter
        self.assertEqual(self.turn().told, [])
        self.capture(five_hour=84)
        self.assertEqual(self.turn().told, ["capacity · five_hour · below threshold"])
        subject, priority, body = self.capacity_events()[1]
        self.assertEqual(priority, "normal")
        self.assertRegex(body, r"^five_hour window is 84% used · back under threshold 90% · resets at ")
        self.assertEqual(ballet_monitor.read_capacity_alerts(), {})

    def test_un_chiffre_qui_oscille_autour_du_seuil_ne_fait_pas_clignoter(self):
        for used in (91, 89, 91, 88, 92, 86, 91):
            self.capture(five_hour=used)
            self.turn()
        self.assertEqual(self.subjects(), ["capacity · five_hour · above threshold"])

    def test_remonte_au_dessus_apres_une_redescente_il_est_signale_de_nouveau(self):
        for used in (93, 70, 91):
            self.capture(five_hour=used)
            self.turn()
        self.assertEqual(self.subjects(), ["capacity · five_hour · above threshold", "capacity · five_hour · below threshold",
                                           "capacity · five_hour · above threshold"])

    def test_la_fenetre_hebdomadaire_est_signalee_en_haute_priorite_avec_son_propre_seuil(self):
        self.set_capacity(seven_day_threshold=80)
        self.capture(five_hour=50, seven_day=82)
        self.assertEqual(self.turn().told, ["capacity · seven_day · above threshold"])
        self.assertEqual(self.capacity_events()[0][1], "high")
        self.assertIn("seven_day window is 82% used · threshold 80%", self.capacity_events()[0][2])

    def test_chaque_fenetre_a_son_etat(self):
        self.capture(five_hour=95, seven_day=95)
        self.assertEqual(sorted(self.turn().told), ["capacity · five_hour · above threshold", "capacity · seven_day · above threshold"])
        self.capture(five_hour=40, seven_day=95)
        self.assertEqual(self.turn().told, ["capacity · five_hour · below threshold"])
        self.assertEqual(list(ballet_monitor.read_capacity_alerts()), ["seven_day"])

    def test_l_etat_garde_le_chiffre_le_reset_et_le_seuil_du_franchissement(self):
        reset = self.capture(five_hour=93)
        self.turn()
        alert = ballet_monitor.read_capacity_alerts()["five_hour"]
        self.assertEqual((alert["used_percent"], alert["resets_at"], alert["threshold"]), (93, reset, 90))
        self.assertTrue(alert["above_since"])

    def test_un_chiffre_perime_est_inconnu_jamais_un_depassement(self):
        self.capture(five_hour=99, minutes_ago=45)
        self.assertEqual(self.turn().told, [])

    def test_un_depassement_dont_le_chiffre_vieillit_redevient_inconnu_et_le_dit(self):
        self.capture(five_hour=93)
        self.turn()
        self.capture(five_hour=93, minutes_ago=45)
        self.assertEqual(self.turn().told, ["capacity · five_hour · below threshold"])
        body = self.capacity_events()[1][2]
        self.assertTrue(body.startswith("five_hour window is unknown: no reading in the last 30 min · it was 93% used · threshold 90%"), body)
        self.assertEqual(ballet_monitor.read_capacity_alerts(), {})

    def test_sans_capture_une_cle_d_api_par_exemple_le_monitor_ne_dit_rien(self):
        self.assertEqual(self.turn().told, [])
        self.assertEqual(self.turn().errors, [])

    def test_un_seuil_a_zero_coupe_la_sonde_de_sa_fenetre(self):
        self.set_capacity(five_hour_threshold=0)
        self.capture(five_hour=99, seven_day=99)
        self.assertEqual(self.turn().told, ["capacity · seven_day · above threshold"])

    def test_couper_la_sonde_pendant_un_depassement_le_leve_et_le_dit(self):
        self.capture(five_hour=93)
        self.turn()
        self.set_capacity(five_hour_threshold=0)
        self.assertEqual(self.turn().told, ["capacity · five_hour · below threshold"])
        self.assertIn("probe is off", self.capacity_events()[1][2])

    def test_les_seuils_et_le_delai_viennent_de_la_config_de_la_machine(self):
        self.set_capacity(five_hour_threshold=70, stale_after_minutes=5)
        self.capture(five_hour=75, minutes_ago=6)
        self.assertEqual(self.turn().told, [])
        self.capture(five_hour=75, minutes_ago=4)
        self.assertEqual(self.turn().told, ["capacity · five_hour · above threshold"])
        self.assertIn("threshold 70%", self.capacity_events()[0][2])

    def test_une_config_invalide_est_une_erreur_du_tour_sans_arreter_les_autres_veilles(self):
        self.set_capacity(five_hour_threshold=150)
        self.queue.queues["antimurphy"] = [item(12)]
        report = self.turn()
        self.assertEqual(report.told, ["antimurphy · ready (1 already)"])
        self.assertTrue(any("five_hour_threshold" in error for error in report.errors), report.errors)

    def test_un_envoi_qui_echoue_n_est_pas_note_et_revient_au_tour_suivant(self):
        self.capture(five_hour=93)
        self.orca.send_failures = 1
        self.assertEqual(len(self.turn().errors), 1)
        self.assertEqual(ballet_monitor.read_capacity_alerts(), {})
        self.assertEqual(self.turn().told, ["capacity · five_hour · above threshold"])

    # --- run ---

    def test_run_enchaine_les_tours_avec_la_pause_entre_deux(self):
        pauses = []
        self.queue.queues["antimurphy"] = []
        with redirect_stdout(io.StringIO()):
            ballet_monitor.run(30, self.orca, self.queue, tours=3, sleep=pauses.append)
        self.assertEqual((len(self.queue.asked), pauses), (3, [30, 30]))

    def test_run_note_sa_version_au_demarrage(self):
        self.queue.queues["antimurphy"] = []
        with mock.patch.object(ballet_monitor.ballet_version, "running", return_value="0.48.0"), redirect_stdout(io.StringIO()):
            ballet_monitor.run(1, self.orca, self.queue, tours=1, sleep=lambda seconds: None)
        self.assertEqual(ballet_runtime.read()["monitor_version"], "0.48.0")

    def test_un_tour_seul_ne_note_pas_de_version(self):
        self.queue.queues["antimurphy"] = []
        with mock.patch.object(ballet_monitor.ballet_version, "running", return_value="0.48.0"):
            ballet_monitor.once(self.orca, self.queue)
        self.assertEqual(ballet_runtime.read()["monitor_version"], "")

    def test_une_version_qui_ne_se_note_pas_n_arrete_pas_run(self):
        self.queue.queues["antimurphy"] = []
        err = io.StringIO()
        with mock.patch.object(ballet_monitor.ballet_runtime, "update", side_effect=OSError("disk full")), redirect_stderr(err), redirect_stdout(io.StringIO()):
            ballet_monitor.run(1, self.orca, self.queue, tours=1, sleep=lambda seconds: None)
        self.assertIn("problem: version not noted: disk full", err.getvalue())
        self.assertEqual(len(self.queue.asked), 1)

    def test_une_erreur_passagere_n_arrete_pas_run(self):
        self.queue.queues["antimurphy"] = ballet_program.ProgramError("gh did not answer")
        err = io.StringIO()
        with redirect_stderr(err):
            ballet_monitor.run(1, self.orca, self.queue, tours=1, sleep=lambda seconds: None)
        self.assertIn("problem: antimurphy: gh did not answer", err.getvalue())

    def test_run_reessaie_au_tour_suivant_et_signale_alors(self):
        self.queue.queues["antimurphy"] = ballet_program.ProgramError("gh did not answer")
        queue = self.queue

        def heals(seconds):
            queue.queues["antimurphy"] = [item(12)]
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            ballet_monitor.run(1, self.orca, self.queue, tours=2, sleep=heals)
        self.assertIn("told Maestro: antimurphy · ready (1 already)", out.getvalue())

    def test_run_survit_meme_a_une_erreur_imprevue(self):
        def broken(home):
            raise RuntimeError("boom")
        err = io.StringIO()
        with redirect_stderr(err):
            ballet_monitor.run(1, self.orca, broken, tours=2, sleep=lambda seconds: None)
        self.assertEqual(err.getvalue().count("problem: turn failed: boom"), 2)

    # --- ligne de commande ---

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ballet_monitor.main(["ballet_monitor.py", *argv], orca=self.orca, queue=self.queue)
        return code, out.getvalue(), err.getvalue()

    def test_once_affiche_ce_qu_il_a_dit_et_sort_avec_zero(self):
        self.queue.queues["antimurphy"] = [item(12)]
        code, out, _ = self.run_main("once")
        self.assertEqual(code, 0)
        self.assertIn("told Maestro: antimurphy · ready (1 already)", out)

    def test_once_sans_rien_de_neuf_le_dit(self):
        self.assertEqual(self.run_main("once")[:2], (0, "nothing new\n"))

    def test_once_sort_avec_un_quand_un_projet_n_a_pas_repondu(self):
        self.queue.queues["antimurphy"] = ballet_program.ProgramError("gh did not answer")
        code, _, err = self.run_main("once")
        self.assertEqual(code, 1)
        self.assertIn("antimurphy: gh did not answer", err)

    def test_un_usage_invalide_sort_avec_deux(self):
        for arguments in ((), ("nap",), ("run", "--interval"), ("run", "--interval", "0"), ("run", "--interval", "vite"), ("once", "now")):
            self.assertEqual(self.run_main(*arguments)[0], 2, arguments)

    def test_run_prend_180_secondes_par_defaut_et_un_intervalle_au_choix(self):
        with mock.patch.object(ballet_monitor, "run") as run:
            ballet_monitor.main(["ballet_monitor.py", "run"], orca=self.orca, queue=self.queue)
            ballet_monitor.main(["ballet_monitor.py", "run", "--interval", "45"], orca=self.orca, queue=self.queue)
        self.assertEqual([call.args[0] for call in run.call_args_list], [180, 45.0])


if __name__ == "__main__":
    unittest.main()
