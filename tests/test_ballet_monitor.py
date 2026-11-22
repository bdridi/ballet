import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ballet_conductors  # noqa: E402
import ballet_maestro  # noqa: E402
import ballet_monitor  # noqa: E402
import ballet_program  # noqa: E402
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
        self.assertEqual(json.loads((self.state / "monitor.json").read_text(encoding="utf-8"))["projects"]["antimurphy"]["ready"][0]["number"], 12)
        self.assertEqual(self.turn().told, [])

    def test_monitor_json_s_ecrit_sans_temporaire_et_sous_son_propre_verrou(self):
        self.queue.queues["antimurphy"] = [item(12)]
        self.turn()
        self.assertEqual(sorted(path.name for path in self.state.iterdir() if path.name.startswith(".")), [])
        self.assertTrue((self.state / "monitor.lock").exists())

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
        self.assertIn("term_9", body)
        line = ballet_conductors.read()["antimurphy#12"]
        self.assertEqual((line["state"], ballet_conductors.state_of(line)), ("gone", "gone"))
        self.assertNotEqual(ballet_conductors.state_of(line), ballet_conductors.RUNNING)

    # --- un Conductor fini resté ouvert ---

    def finished_conductor(self, minutes_ago=30, key="antimurphy#12", terminal="term_9", kind="rehearsal"):
        """Un Conductor lancé (par Maestro si `kind`), fini il y a `minutes_ago` minutes, son terminal encore vivant."""
        from datetime import datetime, timedelta, timezone
        ballet_conductors.record_launch(key, "antimurphy", key.split("#")[1], kind, terminal)
        ballet_conductors.note_events([{"type": "status", "from": terminal, "subject": f"{key} · done"}])
        registry = ballet_conductors.read()
        registry[key]["seen"] = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")
        ballet_conductors._write(registry, None)
        self.orca.terminals.append(terminal)

    def close_after(self, minutes):
        config = ballet_maestro.read_config()
        config["conductors"] = {"close_finished_after_minutes": minutes}
        ballet_maestro.write_config(config)

    def test_un_conductor_fini_reste_ouvert_au_dela_du_delai_est_signale_une_fois(self):
        self.finished_conductor(minutes_ago=30)
        self.assertEqual(self.turn().told, ["antimurphy#12 · finished"])
        subject, priority, body = self.sent()[-1]
        self.assertIn("terminal term_9 is still open after 10 min", body)
        self.assertIn("ballet_launch.py close antimurphy#12", body)
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

    # --- run ---

    def test_run_enchaine_les_tours_avec_la_pause_entre_deux(self):
        pauses = []
        self.queue.queues["antimurphy"] = []
        with redirect_stdout(io.StringIO()):
            ballet_monitor.run(30, self.orca, self.queue, tours=3, sleep=pauses.append)
        self.assertEqual((len(self.queue.asked), pauses), (3, [30, 30]))

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
