import io
import json
import sys
import tempfile
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_conductors  # noqa: E402
import ballet_maestro  # noqa: E402
import ballet_runtime  # noqa: E402
import ballet_rehearsal  # noqa: E402
import ballet_restart  # noqa: E402
import ballet_store  # noqa: E402
from ballet_maestro import MaestroError  # noqa: E402
from ballet_rehearsal import Rehearsal, Session  # noqa: E402

WAITING_PID = 4242   # le pid de l'attente de Maestro, quand sa session dort sur sa boîte


class FakeOrca:
    """La CLI Orca avec les terminaux qu'elle crée et ferme ; chaque commande est notée."""

    def __init__(self):
        self.commands = []
        self.terminals = []
        self.created = 0
        self.unreachable = False

    def __call__(self, arguments):
        self.commands.append(arguments)
        if self.unreachable:
            raise MaestroError("This terminal could not connect to Orca.")
        if arguments[:2] == ["terminal", "list"]:
            return json.dumps({"ok": True, "result": {"terminals": [{"handle": handle} for handle in self.terminals]}})
        if arguments[:2] == ["terminal", "create"]:
            self.created += 1
            self.terminals.append(f"term_{self.created}")
            return json.dumps({"ok": True, "result": {"terminal": {"handle": f"term_{self.created}"}}})
        if arguments[:2] == ["terminal", "close"]:
            handle = arguments[arguments.index("--terminal") + 1]
            self.terminals = [other for other in self.terminals if other != handle]
        if arguments[:2] == ["orchestration", "run-create"]:
            return json.dumps({"ok": True, "result": {"run": {"id": "run_box"}}})
        return "{}"

    def ran(self, *prefix):
        return [command for command in self.commands if command[:len(prefix)] == list(prefix)]


class BalletRestartTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.state = self.root / "ballet-home"
        environment = mock.patch.dict("os.environ", {"BALLET_HOME": str(self.state), "ORCA_TERMINAL_HANDLE": "term_restarter"})
        environment.start()
        self.addCleanup(environment.stop)
        wait_runs = mock.patch.object(ballet_maestro, "_wait_runs", lambda pid: pid == WAITING_PID)
        wait_runs.start()
        self.addCleanup(wait_runs.stop)
        stop_the_wait = mock.patch.object(ballet_maestro, "_stop_the_wait")
        self.stopped_wait = stop_the_wait.start()
        self.addCleanup(stop_the_wait.stop)
        self.orca = FakeOrca()
        self.slept = []
        self.now = 0
        self.on_sleep = []                     # ce qui change pendant que le script dort
        self.home = self.root / "antimurphy"
        self.home.mkdir()
        ballet_maestro.add_project("antimurphy", str(self.home))
        ballet_maestro.mailbox(self.orca)      # term_1 ; la Run de la boîte
        ballet_maestro.maestro(self.orca)      # term_2 : la session Maestro
        self.owner = ballet_maestro.claim().split("owner ")[1]
        self.orca.commands.clear()

    # --- l'environnement ---

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds
        for change in list(self.on_sleep):
            change()

    def run_restart(self):
        return ballet_restart.run(self.orca, sleep=self.sleep, clock=lambda: self.now)

    def sleeping_on_wait(self, sleeping=True):
        ballet_runtime.update(lease_pid=WAITING_PID if sleeping else 0)

    def conductor(self, item="12", terminal="term_9", kind="rehearsal"):
        ballet_conductors.record_launch(f"antimurphy#{item}", "antimurphy", item, kind, terminal)
        self.orca.terminals.append(terminal)

    def session(self, item="#12", status="open", current="FEAT-004.1"):
        ballet_rehearsal._save_session(Session(item=item, issue=item.lstrip("#"), current=current), self.home)
        ballet_rehearsal._save(Rehearsal(id=current, issue=item, repo="repo", status=status), self.home)

    def runtime(self):
        return ballet_runtime.read()

    def paused(self):
        return bool(self.runtime()["paused_at"])

    # --- qui travaille ---

    def test_un_conductor_lance_a_l_instant_sans_session_travaille(self):
        self.conductor()
        self.assertEqual(ballet_restart.working(self.orca), ["antimurphy#12"])

    def test_un_conductor_dont_la_session_est_ouverte_travaille(self):
        self.conductor()
        self.session(status="open")
        self.assertEqual(ballet_restart.working(self.orca), ["antimurphy#12"])

    def test_une_pause_sur_escalade_ne_compte_pas(self):
        self.conductor()
        self.session(status="escalated")
        self.assertEqual(ballet_restart.working(self.orca), [])

    def test_un_workshop_en_escalade_ne_compte_pas_et_un_workshop_ouvert_si(self):
        self.conductor("BUG-004", kind="workshop")
        ballet_store.save(self.home, "workshop", {"item": "BUG-004", "repo": "r", "status": "open"})
        self.assertEqual(ballet_restart.working(self.orca), ["antimurphy#BUG-004"])
        ballet_store.save(self.home, "workshop", {"item": "BUG-004", "repo": "r", "status": "escalated"})
        self.assertEqual(ballet_restart.working(self.orca), [])

    def test_c_est_l_etat_de_la_rehearsal_en_cours_qui_compte_pas_celui_de_la_session(self):
        """Après un `tell`, le dernier événement du registre reste `escalate` alors que le Conductor a repris : le registre ne suffit pas."""
        self.conductor()
        ballet_conductors.note_events([{"type": "status", "from": "term_9", "subject": "antimurphy#12 · escalate"}])
        self.session(status="open")
        self.assertEqual(ballet_restart.working(self.orca), ["antimurphy#12"])

    def test_ne_travaillent_pas_un_terminal_disparu_un_fini_un_arrete(self):
        self.conductor("12", "term_9")
        self.conductor("13", "term_10")
        self.conductor("14", "term_11")
        self.conductor("15", "term_12")
        ballet_conductors.mark_gone("antimurphy#12", "term_9")
        self.orca.terminals.remove("term_10")
        ballet_conductors.note_events([{"type": "status", "from": "term_11", "subject": "antimurphy#14 · done"}])
        ballet_conductors.mark_stopped("antimurphy#15", "term_12")
        self.assertEqual(ballet_restart.working(self.orca), [])

    def test_une_orca_injoignable_leve_au_lieu_de_dire_que_personne_ne_travaille(self):
        self.conductor()
        self.orca.unreachable = True
        with self.assertRaises(MaestroError):
            ballet_restart.working(self.orca)

    # --- la demande ---

    def test_la_demande_refuse_un_jeton_qui_ne_tient_pas_le_bail(self):
        with self.assertRaisesRegex(MaestroError, "not Maestro anymore"):
            ballet_restart.request("autre-jeton", self.orca)
        self.assertFalse(self.paused())

    def test_la_demande_refuse_une_session_hors_du_terminal_de_maestro(self):
        self.orca.terminals.remove("term_2")
        with self.assertRaisesRegex(MaestroError, "does not run in the terminal Maestro owns"):
            ballet_restart.request(self.owner, self.orca)
        self.assertFalse(self.paused())
        self.assertEqual(self.orca.ran("terminal", "create"), [])

    def test_la_demande_pose_le_drapeau_et_cree_le_terminal_du_redemarrage(self):
        report = ballet_restart.request(self.owner, self.orca)
        self.assertTrue(self.paused())
        command = self.orca.ran("terminal", "create")[-1]
        self.assertEqual(command[command.index("--title") + 1], "maestro-restart")
        self.assertIn("ballet_restart.py run", command[command.index("--command") + 1])
        self.assertIn(f"BALLET_HOME={self.state}", command[command.index("--command") + 1])
        self.assertEqual((self.runtime()["restart_terminal"], self.runtime()["restart_owns_pause"]), ("term_3", True))
        self.assertIn("restart scheduled", report)

    def test_un_drapeau_deja_pose_n_est_pas_a_lui_et_ne_sera_pas_retire(self):
        ballet_maestro.pause()
        ballet_restart.request(self.owner, self.orca)
        self.assertEqual(self.runtime()["restart_owns_pause"], False)

    def test_une_demande_en_cours_n_en_cree_pas_une_seconde(self):
        ballet_restart.request(self.owner, self.orca)
        report = ballet_restart.request(self.owner, self.orca)
        self.assertIn("restart already in progress: terminal term_3", report)
        self.assertEqual(len(self.orca.ran("terminal", "create")), 1)

    def test_un_terminal_qui_ne_se_cree_pas_leve_le_drapeau_que_la_demande_venait_de_poser(self):
        original = self.orca.__call__

        def failing(arguments):
            if arguments[:2] == ["terminal", "create"]:
                raise MaestroError("create failed")
            return original(arguments)

        with self.assertRaisesRegex(MaestroError, "create failed"):
            ballet_restart.request(self.owner, failing)
        self.assertFalse(self.paused())
        self.assertEqual(self.runtime()["restart_terminal"], "")

    # --- le redémarrage ---

    def asked(self):
        ballet_restart.request(self.owner, self.orca)
        self.sleeping_on_wait()
        self.orca.commands.clear()

    def new_session_claims_when_created(self):
        """La nouvelle session Maestro prend le bail dès que son terminal existe."""
        def claim():
            if self.orca.ran("terminal", "create") and not self.runtime()["lease_owner"]:
                ballet_maestro.claim()
        self.on_sleep.append(claim)

    def test_il_attend_qu_aucun_conductor_ne_travaille_avant_de_toucher_a_maestro(self):
        self.asked()
        self.conductor()
        self.on_sleep.append(lambda: ballet_conductors.note_events(
            [{"type": "status", "from": "term_9", "subject": "antimurphy#12 · done"}]) if len(self.slept) == 2 else None)
        self.new_session_claims_when_created()
        self.run_restart()
        self.assertGreaterEqual(len(self.slept), 2)
        self.assertEqual(len(self.orca.ran("terminal", "close")), 2)   # Maestro, puis le terminal du redémarrage

    def test_il_n_interrompt_pas_une_session_qui_traite_un_message(self):
        self.asked()
        self.sleeping_on_wait(False)           # le bail est tout frais, aucune attente ne tourne : elle répond à quelqu'un
        self.on_sleep.append(lambda: self.sleeping_on_wait(True) if len(self.slept) == 3 else None)
        self.new_session_claims_when_created()
        self.run_restart()
        self.assertEqual(len(self.slept), 3 + 1)   # trois tours occupés, puis un tour d'attente du nouveau bail
        self.assertEqual(self.orca.ran("terminal", "close")[0][3], "term_2")

    def test_sans_session_vivante_il_remplace_tout_de_suite(self):
        self.asked()
        ballet_runtime.update(**ballet_runtime.empty_lease())
        self.new_session_claims_when_created()
        self.run_restart()
        self.assertEqual(self.orca.ran("terminal", "close")[0][3], "term_2")

    def test_il_ferme_l_ancien_maestro_leve_le_bail_et_en_lance_un_nouveau(self):
        self.asked()
        self.new_session_claims_when_created()
        report = self.run_restart()
        closed = [command[3] for command in self.orca.ran("terminal", "close")]
        self.assertEqual(closed[0], "term_2")
        self.stopped_wait.assert_called()
        created = self.orca.ran("terminal", "create")
        self.assertEqual(created[-1][created[-1].index("--title") + 1], "maestro")
        self.assertEqual(self.runtime()["maestro_terminal"], "term_4")
        self.assertIn("Maestro restarted", report)

    def test_il_retire_le_drapeau_quand_la_nouvelle_session_a_pris_le_bail(self):
        self.asked()
        self.new_session_claims_when_created()
        self.run_restart()
        self.assertFalse(self.paused())
        self.assertEqual(self.runtime()["restart_terminal"], "")
        self.assertNotEqual(self.runtime()["lease_owner"], self.owner)
        self.assertNotEqual(self.runtime()["lease_owner"], "")

    def test_il_garde_le_drapeau_qui_n_etait_pas_a_lui(self):
        ballet_maestro.pause()
        self.asked()
        self.new_session_claims_when_created()
        self.run_restart()
        self.assertTrue(self.paused())

    def test_il_ferme_son_propre_terminal_en_dernier(self):
        self.asked()
        self.new_session_claims_when_created()
        self.run_restart()
        self.assertEqual(self.orca.ran("terminal", "close")[-1][3], "term_restarter")

    def test_apres_quatre_heures_sans_silence_il_abandonne_et_le_dit_dans_la_boite(self):
        self.asked()
        self.conductor()
        self.run_restart()
        self.assertGreaterEqual(self.now, ballet_restart.MAX_WAIT_SECONDS)
        self.assertFalse(self.paused())
        self.assertNotIn("term_2", [command[3] for command in self.orca.ran("terminal", "close")])
        sent = self.orca.ran("orchestration", "send")[0]
        self.assertEqual(sent[sent.index("--subject") + 1], "maestro · restart abandoned")
        self.assertIn("antimurphy#12", sent[sent.index("--body") + 1])
        self.assertEqual(self.runtime()["lease_owner"], self.owner)

    def test_une_nouvelle_session_qui_ne_prend_pas_le_bail_est_dite_et_le_drapeau_leve(self):
        self.asked()
        self.run_restart()
        self.assertGreaterEqual(self.now, ballet_restart.CLAIM_WAIT_SECONDS)
        self.assertFalse(self.paused())
        sent = self.orca.ran("orchestration", "send")[0]
        self.assertEqual(sent[sent.index("--subject") + 1], "maestro · restart abandoned")
        self.assertIn("did not claim the lease", sent[sent.index("--body") + 1])

    def test_une_orca_injoignable_pendant_l_attente_est_reessayee(self):
        self.asked()
        self.orca.unreachable = True
        self.on_sleep.append(lambda: setattr(self.orca, "unreachable", False) if len(self.slept) == 2 else None)
        self.new_session_claims_when_created()
        self.run_restart()
        self.assertGreaterEqual(len(self.slept), 2)
        self.assertFalse(self.paused())

    # --- la ligne de commande ---

    def run_main(self, *arguments):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ballet_restart.main(["ballet_restart.py", *arguments], orca=self.orca)
        return code, out.getvalue(), err.getvalue()

    def test_when_idle_en_ligne_de_commande(self):
        code, out, err = self.run_main("when-idle", "--owner", self.owner)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("restart scheduled", out)

    def test_un_refus_sort_avec_1_et_un_message_en_anglais(self):
        code, out, err = self.run_main("when-idle", "--owner", "autre")
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("restart: this session is not Maestro anymore"))

    def test_un_usage_invalide_sort_avec_2(self):
        for arguments in ((), ("when-idle",), ("when-idle", "--owner"), ("now",)):
            code, _, err = self.run_main(*arguments)
            self.assertEqual(code, 2)
            self.assertIn("usage:", err)


if __name__ == "__main__":
    unittest.main()
