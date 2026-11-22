import io
import json
import shlex
import sys
import tempfile
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_conductors  # noqa: E402
import ballet_maestro  # noqa: E402
from ballet_rehearsal import Rehearsal, Session, Step  # noqa: E402
from ballet_workshop import Workshop  # noqa: E402


class FakeOrca:
    """La CLI Orca, avec juste ce que Maestro lit ; chaque commande est notée."""

    def __init__(self):
        self.commands = []
        self.terminals = []          # les terminaux vivants
        self.created = 0
        self.unreachable = False     # Orca ne répond pas
        self.run_failures = 0        # `run-create` échoue ces fois-ci
        self.send_failures = 0       # `send` échoue ces fois-ci
        self.batches = []            # les lots que `check --wait` rend, un par appel ; un appel de plus expire sans message
        self.history = []            # les messages de `inbox`, du plus récent au plus ancien

    def __call__(self, arguments):
        self.commands.append(arguments)
        if self.unreachable:
            raise ballet_maestro.MaestroError("This terminal could not connect to Orca.")
        if arguments[:2] == ["terminal", "list"]:
            return json.dumps({"ok": True, "result": {"terminals": [{"handle": handle} for handle in self.terminals]}})
        if arguments[:2] == ["terminal", "create"]:
            self.created += 1
            self.terminals.append(f"term_{self.created}")
            return json.dumps({"ok": True, "result": {"terminal": {"handle": f"term_{self.created}", "title": "maestro-mailbox"}}})
        if arguments[:2] == ["orchestration", "run-create"]:
            if self.run_failures:
                self.run_failures -= 1
                raise ballet_maestro.MaestroError("run-create failed")
            return json.dumps({"ok": True, "result": {"run": {"id": f"run_{self.created}", "from": arguments[arguments.index("--from") + 1]}}})
        if arguments[:2] == ["orchestration", "send"] and self.send_failures:
            self.send_failures -= 1
            raise ballet_maestro.MaestroError("no_active_sender_terminal")
        if arguments[:2] == ["orchestration", "check"]:
            messages = self.batches.pop(0) if self.batches else []
            return json.dumps({"ok": True, "result": {"messages": messages, **({} if messages else {"timedOut": True})}})
        if arguments[:2] == ["orchestration", "inbox"]:
            run = arguments[arguments.index("--terminal") + 1].removeprefix("run:")
            return json.dumps({"ok": True, "result": {"messages": [row for row in self.history if row["run_id"] == run]}})
        return "{}"

    def ran(self, *prefix):
        return [command for command in self.commands if command[:len(prefix)] == list(prefix)]


class BalletMaestroTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.state = self.root / "ballet-home"
        environment = mock.patch.dict("os.environ", {"BALLET_HOME": str(self.state)})
        environment.start()
        self.addCleanup(environment.stop)
        self.orca = FakeOrca()
        self.live = None            # ce que GitHub rend quand `ready` relit les bloqueurs ; None : injoignable
        self.live_reads = []
        live = mock.patch.object(ballet_maestro, "_live_ready", side_effect=self.read_live)
        live.start()
        self.addCleanup(live.stop)

    def read_live(self, project_dir):
        self.live_reads.append(project_dir)
        return self.live

    def config(self):
        return tomllib.loads((self.state / "maestro.toml").read_text(encoding="utf-8"))

    def project(self, name):
        folder = self.root / name
        folder.mkdir()
        return folder

    # --- maestro.toml ---

    def test_le_toml_ecrit_se_relit_a_l_identique(self):
        config = {"mailbox": {"terminal": "term_1", "run": "run_1"}, "lease": {"owner": "abc", "pid": 4242, "renewed": "2026-11-21T08:00:00+00:00"},
                  "monitor": {"terminal": "term_3"},
                  "projects": {"antimurphy": {"path": "/p/antimurphy", "auto_launch": ["Task", "Bug"]},
                               "mon projet": {"path": "/p/\"quoted\" été\n"}},
                  "limits": {"max_running": 3}}
        ballet_maestro.write_config(config)
        self.assertEqual(self.config(), config)

    def test_le_toml_reserve_le_bail_et_reste_lisible(self):
        ballet_maestro.write_config(ballet_maestro.read_config())
        text = (self.state / "maestro.toml").read_text(encoding="utf-8")
        self.assertIn("[lease]\nowner = \"\"\npid = 0\nrenewed = \"\"", text)
        self.assertEqual(self.config()["lease"], {"owner": "", "pid": 0, "renewed": ""})

    def test_sans_fichier_l_etat_est_vide(self):
        self.assertEqual(ballet_maestro.read_config(), {"mailbox": {}, "lease": {"owner": "", "pid": 0, "renewed": ""}, "projects": {}})

    def test_une_ecriture_interrompue_laisse_l_ancien_fichier_entier_et_aucun_temporaire(self):
        ballet_maestro.write_config({"mailbox": {"run": "run_old"}})
        with mock.patch.object(ballet_maestro, "to_toml", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            ballet_maestro.write_config({"mailbox": {"run": "run_new"}})
        self.assertEqual(self.config()["mailbox"], {"run": "run_old"})
        self.assertEqual(sorted(path.name for path in self.state.iterdir()), ["maestro.toml"])

    def test_l_ecriture_remplace_le_fichier_par_un_renommage(self):
        with mock.patch.object(ballet_maestro.os, "replace", wraps=ballet_maestro.os.replace) as replace:
            ballet_maestro.write_config({"mailbox": {}})
        source, target = replace.call_args.args
        self.assertEqual(Path(target), self.state / "maestro.toml")
        self.assertEqual(Path(source).parent, self.state)

    # --- mailbox ---

    def test_mailbox_cree_un_terminal_vide_puis_une_run_depuis_lui_et_les_note(self):
        output = ballet_maestro.mailbox(self.orca)
        self.assertEqual(output, "mailbox created: terminal term_1, run:run_1")
        create = self.orca.ran("terminal", "create")[0]
        self.assertEqual(create[create.index("--title") + 1], "maestro-mailbox")
        self.assertNotIn("--command", create)
        run = self.orca.ran("orchestration", "run-create")[0]
        self.assertEqual(run[run.index("--from") + 1], "term_1")
        self.assertEqual(self.config()["mailbox"], {"terminal": "term_1", "run": "run_1"})

    def test_mailbox_est_idempotent_tant_que_le_terminal_vit(self):
        ballet_maestro.mailbox(self.orca)
        output = ballet_maestro.mailbox(self.orca)
        self.assertEqual(output, "mailbox already there: terminal term_1, run:run_1")
        self.assertEqual(len(self.orca.ran("terminal", "create")), 1)
        self.assertEqual(len(self.orca.ran("orchestration", "run-create")), 1)

    def test_un_terminal_disparu_est_remplace_et_l_ancienne_run_gardee_pour_une_derniere_lecture(self):
        ballet_maestro.mailbox(self.orca)
        self.orca.terminals.clear()
        self.assertEqual(ballet_maestro.mailbox(self.orca), "mailbox created: terminal term_2, run:run_2")
        self.assertEqual(self.config()["mailbox"], {"terminal": "term_2", "run": "run_2", "previous_run": "run_1"})

    def test_une_orca_injoignable_ne_cree_rien(self):
        ballet_maestro.write_config({"mailbox": {"terminal": "term_1", "run": "run_1"}})
        self.orca.unreachable = True
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.mailbox(self.orca)
        self.assertEqual(self.orca.ran("terminal", "create"), [])
        self.assertEqual(self.config()["mailbox"], {"terminal": "term_1", "run": "run_1"})

    def test_une_run_qui_echoue_garde_le_terminal_et_l_appel_suivant_ne_cree_que_la_run(self):
        self.orca.run_failures = 1
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.mailbox(self.orca)
        self.assertEqual(self.config()["mailbox"], {"terminal": "term_1"})
        self.assertEqual(ballet_maestro.mailbox(self.orca), "mailbox created: terminal term_1, run:run_1")
        self.assertEqual(len(self.orca.ran("terminal", "create")), 1)

    def test_mailbox_garde_les_projets_et_le_bail(self):
        ballet_maestro.add_project("antimurphy", str(self.project("antimurphy")))
        ballet_maestro.mailbox(self.orca)
        self.assertIn("antimurphy", self.config()["projects"])
        self.assertEqual(self.config()["lease"], {"owner": "", "pid": 0, "renewed": ""})

    def test_un_ancien_bail_sans_proprietaire_se_relit_avec_les_trois_cles(self):
        self.state.mkdir()
        (self.state / "maestro.toml").write_text('[lease]\npid = 0\nsince = ""\n', encoding="utf-8")
        self.assertEqual(ballet_maestro.read_config()["lease"], {"owner": "", "pid": 0, "renewed": ""})

    # --- projets ---

    def test_project_add_enregistre_le_chemin_absolu_et_list_les_montre(self):
        folder = self.project("antimurphy")
        self.assertEqual(ballet_maestro.add_project("antimurphy", str(folder)), f"project antimurphy: {folder.resolve()}")
        self.assertEqual(ballet_maestro.list_projects(), f"antimurphy  {folder.resolve()}")

    def test_project_add_refuse_un_alias_invalide_ou_un_dossier_absent(self):
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.add_project("Anti Murphy", str(self.project("x")))
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.add_project("antimurphy", str(self.root / "missing"))

    def test_sans_projet_list_dit_comment_en_ajouter(self):
        self.assertIn("project add", ballet_maestro.list_projects())

    # --- l'annonce des Conductors ---

    def test_sans_toml_l_annonce_ne_fait_rien_en_silence(self):
        step = Step("escalate", "plan to review", ["- x"], item="#12")
        ballet_maestro.announce(step, self.root, self.orca)
        self.assertEqual(self.orca.commands, [])
        self.assertEqual(step.done, ["- x"])

    def test_sans_boite_l_annonce_ne_fait_rien(self):
        ballet_maestro.add_project("antimurphy", str(self.project("antimurphy")))
        step = Step("done", item="#12")
        ballet_maestro.announce(step, self.root / "antimurphy", self.orca)
        self.assertEqual(self.orca.commands, [])

    def test_l_annonce_envoie_un_status_haute_priorite_sous_l_alias_du_projet(self):
        folder = self.project("antimurphy")
        ballet_maestro.write_config({"mailbox": {"run": "run_box"}, "projects": {"am": {"path": str(folder)}}})
        step = Step("escalate", "plan to review", item="#12")
        ballet_maestro.announce(step, folder, self.orca)
        send = self.orca.ran("orchestration", "send")[0]
        self.assertEqual(send[send.index("--to") + 1], "run:run_box")
        self.assertEqual(send[send.index("--type") + 1], "status")
        self.assertEqual(send[send.index("--priority") + 1], "high")
        self.assertEqual(send[send.index("--subject") + 1], "am#12 · escalate")
        self.assertEqual(send[send.index("--body") + 1], "NEXT: escalate plan to review")
        self.assertEqual(step.done, ["Maestro told: am#12 · escalate"])

    def test_un_echec_d_envoi_devient_un_avertissement_sans_rien_lever(self):
        ballet_maestro.write_config({"mailbox": {"run": "run_box"}})
        self.orca.send_failures = 1
        step = Step("done", item="BUG-004")
        ballet_maestro.announce(step, self.project("antimurphy"), self.orca)
        self.assertEqual(step.done, ["Maestro not told (antimurphy#BUG-004 · done): no_active_sender_terminal"])

    def test_un_toml_illisible_devient_un_avertissement(self):
        self.state.mkdir()
        (self.state / "maestro.toml").write_text("[mailbox\n", encoding="utf-8")
        step = Step("done", item="#12")
        ballet_maestro.announce(step, self.root, self.orca)
        self.assertTrue(step.done[0].startswith("Maestro not told:"))
        self.assertEqual(self.orca.commands, [])

    def test_seuls_l_escalade_et_la_fin_d_une_transition_sont_annoncees(self):
        ballet_maestro.write_config({"mailbox": {"run": "run_box"}})
        for step in (Step("wait", item="#12"), Step("escalate", "a read")):
            ballet_maestro.announce(step, self.root, self.orca)
        self.assertEqual(self.orca.commands, [])

    # --- le bail ---

    def hold_lease(self, owner="other", pid=0, age=timedelta(0)):
        """Le bail d'une autre session, renouvelé il y a `age`."""
        config = ballet_maestro.read_config()
        renewed = (datetime.now(timezone.utc) - age).isoformat(timespec="seconds")
        config["lease"] = {"owner": owner, "pid": pid, "renewed": renewed}
        ballet_maestro.write_config(config)

    def waiting(self, running=True):
        """`ps` voit (ou non) une attente de Maestro tourner sous un pid."""
        patch = mock.patch.object(ballet_maestro, "_wait_runs", return_value=running)
        patch.start()
        self.addCleanup(patch.stop)

    def test_claim_libre_ecrit_un_jeton_et_l_affiche(self):
        output = ballet_maestro.claim()
        lease = self.config()["lease"]
        self.assertEqual(output, f"lease claimed, owner {lease['owner']}")
        self.assertRegex(lease["owner"], r"^[0-9a-f]{16}$")
        self.assertEqual(lease["pid"], 0)
        self.assertTrue(lease["renewed"])

    def test_claim_refuse_un_bail_renouvele_il_y_a_moins_de_dix_minutes_et_propose_take_over(self):
        self.hold_lease(age=timedelta(minutes=9))
        with self.assertRaises(ballet_maestro.MaestroError) as refused:
            ballet_maestro.claim()
        self.assertIn("claim --take-over", str(refused.exception))
        self.assertEqual(self.config()["lease"]["owner"], "other")

    def test_claim_refuse_un_bail_dont_l_attente_tourne_meme_ancien(self):
        self.hold_lease(pid=4242, age=timedelta(hours=3))
        self.waiting(running=True)
        with self.assertRaises(ballet_maestro.MaestroError) as refused:
            ballet_maestro.claim()
        self.assertIn("pid 4242", str(refused.exception))

    def test_claim_prend_un_bail_expire(self):
        self.hold_lease(age=timedelta(minutes=11))
        self.waiting(running=False)
        ballet_maestro.claim()
        self.assertNotEqual(self.config()["lease"]["owner"], "other")

    def test_claim_prend_un_bail_sans_proprietaire(self):
        ballet_maestro.write_config(ballet_maestro.read_config())
        ballet_maestro.claim()
        self.assertTrue(self.config()["lease"]["owner"])

    def test_take_over_arrete_l_attente_de_l_ancien_puis_prend_le_bail(self):
        self.hold_lease(pid=4242, age=timedelta(minutes=1))
        self.waiting(running=True)
        with mock.patch.object(ballet_maestro.os, "kill") as kill:
            ballet_maestro.claim(take_over=True)
        kill.assert_called_once_with(4242, ballet_maestro.signal.SIGTERM)
        lease = self.config()["lease"]
        self.assertNotEqual(lease["owner"], "other")
        self.assertEqual(lease["pid"], 0)

    def test_take_over_sans_attente_vivante_ne_tue_rien(self):
        self.hold_lease(pid=4242, age=timedelta(minutes=1))
        self.waiting(running=False)
        with mock.patch.object(ballet_maestro.os, "kill") as kill:
            ballet_maestro.claim(take_over=True)
        kill.assert_not_called()
        self.assertNotEqual(self.config()["lease"]["owner"], "other")

    def test_deux_claims_tour_a_tour_le_second_est_refuse(self):
        ballet_maestro.claim()
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.claim()

    # --- wait ---

    def message(self, subject="antimurphy#12 · escalate", body="NEXT: escalate plan to review", sender="term_9", kind="status", priority="high"):
        return {"id": "msg_1", "type": kind, "from": sender, "subject": subject, "body": body, "priority": priority}

    def claimed(self):
        """Une session Maestro prête à attendre : la boîte, le bail pris. Rend son jeton."""
        ballet_maestro.mailbox(self.orca)
        return ballet_maestro.claim().rsplit(" ", 1)[1]

    def test_wait_refuse_un_jeton_qui_ne_tient_pas_le_bail(self):
        self.claimed()
        with self.assertRaises(ballet_maestro.MaestroError) as refused:
            ballet_maestro.wait("not-the-token", self.orca)
        self.assertTrue(str(refused.exception).startswith("this session is not Maestro anymore: "))
        self.assertEqual(self.orca.ran("orchestration", "check"), [])

    def test_wait_sans_bail_dit_de_le_prendre(self):
        ballet_maestro.mailbox(self.orca)
        with self.assertRaises(ballet_maestro.MaestroError) as refused:
            ballet_maestro.wait("abc", self.orca)
        self.assertIn("run claim", str(refused.exception))

    def test_wait_sans_boite_dit_de_la_creer(self):
        self.hold_lease(owner="abc")
        with self.assertRaises(ballet_maestro.MaestroError) as refused:
            ballet_maestro.wait("abc", self.orca)
        self.assertIn("mailbox", str(refused.exception))

    def test_wait_lit_la_boite_en_consommant_jamais_en_peek(self):
        owner = self.claimed()
        self.orca.batches = [[self.message()]]
        ballet_maestro.wait(owner, self.orca)
        check = self.orca.ran("orchestration", "check")[0]
        self.assertEqual(check[check.index("--terminal") + 1], "term_1")
        self.assertEqual(check[check.index("--run") + 1], "run_1")
        for option in ("--wait", "--json"):
            self.assertIn(option, check)
        self.assertNotIn("--peek", check)

    def test_wait_affiche_sujet_priorite_expediteur_et_corps(self):
        owner = self.claimed()
        self.orca.batches = [[self.message(body="NEXT: escalate plan to review\nlink: https://x/1")]]
        output = ballet_maestro.wait(owner, self.orca)
        self.assertIn("[high] status from term_9", output)
        self.assertIn("Subject: antimurphy#12 · escalate", output)
        self.assertIn("NEXT: escalate plan to review\nlink: https://x/1", output)

    def test_wait_attend_encore_quand_l_attente_expire_sans_message(self):
        owner = self.claimed()
        self.orca.batches = [[], [self.message()]]
        self.assertIn("antimurphy#12", ballet_maestro.wait(owner, self.orca))
        self.assertEqual(len(self.orca.ran("orchestration", "check")), 2)

    def test_wait_note_le_pid_pendant_l_attente_puis_le_remet_a_zero_et_renouvelle(self):
        owner = self.claimed()
        seen = {}
        original = self.orca.__call__

        def spying(arguments):
            if arguments[:2] == ["orchestration", "check"]:
                seen.update(self.config()["lease"])
            return original(arguments)
        self.orca.batches = [[self.message()]]
        ballet_maestro.wait(owner, spying)
        self.assertEqual(seen["pid"], ballet_maestro.os.getpid())
        lease = self.config()["lease"]
        self.assertEqual((lease["owner"], lease["pid"]), (owner, 0))
        self.assertGreaterEqual(lease["renewed"], seen["renewed"])

    def test_wait_remet_le_pid_a_zero_meme_quand_orca_tombe(self):
        owner = self.claimed()
        self.orca.unreachable = True
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.wait(owner, self.orca)
        self.assertEqual(self.config()["lease"]["pid"], 0)

    def test_wait_arrete_par_un_take_over_ne_touche_pas_au_nouveau_bail(self):
        owner = self.claimed()

        def taken_over(arguments):
            if arguments[:2] == ["orchestration", "check"]:
                self.hold_lease(owner="new-owner", pid=0)
                raise ballet_maestro.MaestroError("stopped")
            return self.orca(arguments)
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.wait(owner, taken_over)
        self.assertEqual(self.config()["lease"]["owner"], "new-owner")

    def test_wait_refuse_une_seconde_attente_du_meme_jeton(self):
        owner = self.claimed()
        self.hold_lease(owner=owner, pid=4242)
        self.waiting(running=True)
        with self.assertRaises(ballet_maestro.MaestroError) as refused:
            ballet_maestro.wait(owner, self.orca)
        self.assertIn("one at a time", str(refused.exception))

    def test_wait_note_le_terminal_expediteur_de_chaque_status_d_un_conductor(self):
        owner = self.claimed()
        self.orca.batches = [[self.message(), self.message(subject="am#BUG-004 · done", sender="term_7"),
                              self.message(subject="note", sender="term_5"), self.message(kind="worker_done", sender="term_6")]]
        ballet_maestro.wait(owner, self.orca)
        registry = json.loads((self.state / "conductors.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(registry), ["am#BUG-004", "antimurphy#12"])
        self.assertEqual(registry["antimurphy#12"]["terminal"], "term_9")
        self.assertEqual(registry["antimurphy#12"]["event"], "escalate")
        self.assertEqual(registry["am#BUG-004"]["event"], "done")
        self.assertTrue(registry["antimurphy#12"]["seen"])

    def test_wait_garde_les_conductors_deja_notes_et_remplace_celui_qui_reecrit(self):
        owner = self.claimed()
        self.orca.batches = [[self.message(sender="term_9")], [self.message(sender="term_10", subject="antimurphy#12 · done")],
                             [self.message(sender="term_11", subject="am#3 · escalate")]]
        for _ in range(3):
            ballet_maestro.wait(owner, self.orca)
        registry = ballet_conductors.read()
        self.assertEqual({key: value["terminal"] for key, value in registry.items()}, {"antimurphy#12": "term_10", "am#3": "term_11"})

    def test_wait_sans_status_de_conductor_n_ecrit_pas_de_registre(self):
        owner = self.claimed()
        self.orca.batches = [[self.message(kind="worker_done", subject="spike ok")]]
        ballet_maestro.wait(owner, self.orca)
        self.assertFalse((self.state / "conductors.json").exists())

    # --- recap ---

    def row(self, sequence, run="run_1", read=1, subject="antimurphy#12 · escalate", body="b"):
        return {"id": f"msg_{sequence}", "run_id": run, "from_handle": "term_9", "to_handle": f"run:{run}", "subject": subject,
                "body": body, "type": "status", "priority": "high", "read": read, "sequence": sequence,
                "created_at": "2026-11-21T13:46:09Z"}

    def test_recap_montre_l_historique_du_plus_ancien_au_plus_recent_et_marque_le_non_lu_consomme(self):
        owner = self.claimed()
        self.orca.batches = [[{"id": "msg_3", "type": "status", "from": "term_9", "subject": "am#3 · done"}]]
        self.orca.history = [self.row(3, read=0, subject="am#3 · done"), self.row(2, subject="am#2 · escalate"), self.row(1, subject="am#1 · done")]
        output = ballet_maestro.recap(owner, self.orca)
        self.assertLess(output.index("am#1"), output.index("am#2"))
        self.assertLess(output.index("am#2"), output.index("am#3"))
        self.assertIn("3 message(s), 1 unread until now", output)
        self.assertIn("· unread\nSubject: am#3 · done", output)
        self.assertIn("· read\nSubject: am#1 · done", output)

    def test_recap_consomme_le_non_lu_sans_attendre_et_note_ses_conductors(self):
        owner = self.claimed()
        self.orca.batches = [[{"id": "msg_1", "type": "status", "from": "term_9", "subject": "antimurphy#12 · escalate"}]]
        ballet_maestro.recap(owner, self.orca)
        check = self.orca.ran("orchestration", "check")[0]
        self.assertNotIn("--wait", check)
        self.assertNotIn("--peek", check)
        self.assertEqual(ballet_conductors.read()["antimurphy#12"]["terminal"], "term_9")
        inbox = self.orca.ran("orchestration", "inbox")[0]
        self.assertEqual(inbox[inbox.index("--terminal") + 1], "run:run_1")
        self.assertIn("--full", inbox)

    def test_recap_refuse_un_jeton_qui_ne_tient_pas_le_bail(self):
        self.claimed()
        with self.assertRaisesRegex(ballet_maestro.MaestroError, "not Maestro anymore"):
            ballet_maestro.recap("someone-else", self.orca)
        self.assertEqual(self.orca.ran("orchestration", "check"), [])

    def test_recap_ne_garde_que_les_derniers_messages(self):
        owner = self.claimed()
        self.orca.history = [self.row(number, subject=f"am#{number} · done") for number in range(30, 0, -1)]
        output = ballet_maestro.recap(owner, self.orca)
        self.assertIn("10 message(s)", output)
        self.assertIn("am#30 · done", output)
        self.assertNotIn("am#20 · done", output)

    def test_recap_relit_la_run_precedente_puis_l_oublie(self):
        owner = self.claimed()
        config = ballet_maestro.read_config()
        config["mailbox"]["previous_run"] = "run_0"
        ballet_maestro.write_config(config)
        self.orca.history = [self.row(2, subject="am#2 · done"), self.row(1, run="run_0", subject="old#1 · escalate")]
        output = ballet_maestro.recap(owner, self.orca)
        self.assertIn("old#1 · escalate", output)
        self.assertNotIn("previous_run", self.config()["mailbox"])
        self.assertNotIn("old#1", ballet_maestro.recap(owner, self.orca))

    def test_recap_d_une_boite_vide_le_dit(self):
        owner = self.claimed()
        self.assertEqual(ballet_maestro.recap(owner, self.orca), "the mailbox is empty")

    def test_recap_sans_boite_dit_de_la_creer(self):
        owner = ballet_maestro.claim().split()[-1]
        with self.assertRaisesRegex(ballet_maestro.MaestroError, "no mailbox yet"):
            ballet_maestro.recap(owner, self.orca)

    # --- status ---

    def open_session(self, folder, item, current="", rehearsal_status="open"):
        """Une session de Rehearsal ouverte dans le projet, avec sa Rehearsal en cours ; les fonctions du script la relisent."""
        import ballet_rehearsal
        ballet_rehearsal._save_session(Session(item=item, current=current), folder)
        if current:
            ballet_rehearsal._save(Rehearsal(id=current, issue=item, repo="repo", status=rehearsal_status), folder)

    def test_status_liste_une_ligne_par_session_ouverte_avec_son_terminal(self):
        folder = self.project("antimurphy")
        ballet_maestro.add_project("antimurphy", str(folder))
        self.open_session(folder, "#12", current="FEAT-004.1", rehearsal_status="escalated")
        self.open_session(folder, "FEAT-005")
        (self.state / "conductors.json").write_text(json.dumps({"antimurphy#12": {"terminal": "term_9", "seen": "x", "event": "escalate"}}), encoding="utf-8")
        lines = ballet_maestro.status(self.orca).splitlines()
        self.assertEqual(lines[:2], ["antimurphy  #12  FEAT-004.1  escalated  term_9",
                                     "antimurphy  FEAT-005  -  open  no terminal known"])

    def test_status_montre_aussi_les_workshops_ouverts_et_ignore_les_sessions_finies(self):
        import ballet_rehearsal
        folder = self.project("antimurphy")
        ballet_maestro.add_project("antimurphy", str(folder))
        ballet_rehearsal._save_session(Session(item="#3", status="done"), folder)
        run = folder / ".ballet" / "run"
        (run / "workshop-OPP-12.json").write_text(json.dumps({"item": "OPP-12", "repo": "r", "status": "escalated"}), encoding="utf-8")
        (run / "workshop-OPP-13.json").write_text(json.dumps({"item": "OPP-13", "repo": "r", "status": "done"}), encoding="utf-8")
        self.assertEqual(ballet_maestro.status(self.orca), "antimurphy  OPP-12  Workshop  escalated  no terminal known")

    def test_status_sans_session_ni_dossier_run_le_dit_et_ne_cree_rien(self):
        folder = self.project("antimurphy")
        ballet_maestro.add_project("antimurphy", str(folder))
        self.assertEqual(ballet_maestro.status(self.orca), "no open session in any project")
        self.assertFalse((folder / ".ballet").exists())

    def test_status_parcourt_chaque_projet(self):
        for name, item in (("beta", "#2"), ("alpha", "#1")):
            folder = self.project(name)
            ballet_maestro.add_project(name, str(folder))
            self.open_session(folder, item)
        self.assertEqual([line.split()[0] for line in ballet_maestro.status(self.orca).splitlines()], ["alpha", "beta"])

    # --- tell ---

    def known_conductor(self, handle="term_9"):
        self.state.mkdir(exist_ok=True)
        (self.state / "conductors.json").write_text(json.dumps({"antimurphy#12": {"terminal": handle, "seen": "x", "event": "escalate"}}), encoding="utf-8")

    def test_tell_ecrit_la_reponse_du_director_dans_le_terminal_du_conductor(self):
        self.known_conductor()
        self.orca.terminals.append("term_9")
        self.assertEqual(ballet_maestro.tell("antimurphy#12", "approve the plan", self.orca), "told antimurphy#12 (terminal term_9)")
        send = self.orca.ran("terminal", "send")[0]
        self.assertEqual(send[send.index("--terminal") + 1], "term_9")
        self.assertEqual(send[send.index("--text") + 1], "Director answers: approve the plan")
        self.assertIn("--enter", send)

    def test_tell_refuse_un_element_inconnu_et_liste_ceux_qu_il_connait(self):
        self.known_conductor()
        with self.assertRaises(ballet_maestro.MaestroError) as refused:
            ballet_maestro.tell("antimurphy#99", "x", self.orca)
        self.assertIn("no terminal known for antimurphy#99", str(refused.exception))
        self.assertIn("antimurphy#12", str(refused.exception))
        self.assertEqual(self.orca.ran("terminal", "send"), [])

    def test_tell_refuse_une_cible_mal_ecrite(self):
        with self.assertRaises(ballet_maestro.MaestroError) as refused:
            ballet_maestro.tell("antimurphy-12", "x", self.orca)
        self.assertIn("<project>#<item>", str(refused.exception))

    def test_tell_refuse_un_terminal_mort(self):
        self.known_conductor("term_gone")
        with self.assertRaises(ballet_maestro.MaestroError) as refused:
            ballet_maestro.tell("antimurphy#12", "x", self.orca)
        self.assertIn("is gone", str(refused.exception))
        self.assertEqual(self.orca.ran("terminal", "send"), [])


    # --- monitor ---

    def test_monitor_cree_le_terminal_du_monitor_avec_sa_commande_et_le_note(self):
        self.assertEqual(ballet_maestro.monitor(self.orca), "monitor created: terminal term_1")
        create = self.orca.ran("terminal", "create")[0]
        self.assertEqual(create[create.index("--title") + 1], "ballet-monitor")
        command = create[create.index("--command") + 1]
        self.assertTrue(command.startswith(f"BALLET_HOME={self.state} python3 "), command)
        self.assertTrue(command.endswith("ballet_monitor.py run"), command)
        self.assertEqual(self.config()["monitor"], {"terminal": "term_1"})

    def test_monitor_sans_ballet_home_ne_transmet_rien(self):
        with mock.patch.dict("os.environ", clear=False) as environment:
            environment.pop("BALLET_HOME")
            self.assertEqual(ballet_maestro._monitor_command()[:8], "python3 ")

    def test_monitor_est_idempotent_tant_que_le_terminal_vit(self):
        ballet_maestro.monitor(self.orca)
        self.assertEqual(ballet_maestro.monitor(self.orca), "monitor already there: terminal term_1")
        self.assertEqual(len(self.orca.ran("terminal", "create")), 1)

    def test_monitor_remplace_un_terminal_disparu(self):
        ballet_maestro.monitor(self.orca)
        self.orca.terminals.clear()
        self.assertEqual(ballet_maestro.monitor(self.orca), "monitor created: terminal term_2")

    def test_monitor_avec_une_orca_injoignable_ne_cree_rien(self):
        ballet_maestro.write_config({"monitor": {"terminal": "term_1"}})
        self.orca.unreachable = True
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.monitor(self.orca)
        self.assertEqual(self.orca.ran("terminal", "create"), [])

    def test_monitor_ne_touche_ni_a_la_boite_ni_aux_projets(self):
        ballet_maestro.mailbox(self.orca)
        ballet_maestro.add_project("antimurphy", str(self.project("antimurphy")))
        ballet_maestro.monitor(self.orca)
        config = self.config()
        self.assertEqual((config["mailbox"], sorted(config["projects"])), ({"terminal": "term_1", "run": "run_1"}, ["antimurphy"]))

    # --- maestro (la session elle-même) ---

    def test_maestro_cree_le_terminal_de_la_session_avec_sa_commande_et_le_note(self):
        with mock.patch.dict("os.environ", clear=False) as environment:
            environment.pop("BALLET_MAESTRO_COMMAND", None)
            self.assertEqual(ballet_maestro.maestro(self.orca), "maestro created: terminal term_1")
        create = self.orca.ran("terminal", "create")[0]
        self.assertEqual(create[create.index("--title") + 1], "maestro")
        self.assertEqual(create[create.index("--command") + 1],
                         f"BALLET_HOME={self.state} claude --remote-control 'ballet maestro' /ballet:maestro")
        self.assertEqual(self.config()["maestro"], {"terminal": "term_1"})

    def test_maestro_sans_ballet_home_ne_transmet_rien(self):
        with mock.patch.dict("os.environ", clear=False) as environment:
            environment.pop("BALLET_HOME")
            environment.pop("BALLET_MAESTRO_COMMAND", None)
            self.assertEqual(ballet_maestro._maestro_command(), "claude --remote-control 'ballet maestro' /ballet:maestro")

    def test_maestro_le_prompt_vient_avant_toute_option(self):
        with mock.patch.dict("os.environ", {"BALLET_MAESTRO_COMMAND": "echo fake-maestro"}):
            words = shlex.split(ballet_maestro._maestro_command())
        self.assertEqual(words[1:], ["echo", "fake-maestro", "--remote-control", "ballet maestro", "/ballet:maestro"])

    def test_maestro_est_idempotent_tant_que_le_terminal_vit(self):
        ballet_maestro.maestro(self.orca)
        self.assertEqual(ballet_maestro.maestro(self.orca), "maestro already there: terminal term_1")
        self.assertEqual(len(self.orca.ran("terminal", "create")), 1)

    def test_maestro_remplace_un_terminal_disparu(self):
        ballet_maestro.maestro(self.orca)
        self.orca.terminals.clear()
        self.assertEqual(ballet_maestro.maestro(self.orca), "maestro created: terminal term_2")

    def test_maestro_ne_cree_rien_quand_une_session_tient_un_bail_vivant_et_le_dit(self):
        ballet_maestro.claim()
        message = ballet_maestro.maestro(self.orca)
        self.assertTrue(message.startswith("maestro not created: another Maestro session holds the lease"), message)
        self.assertIn("claim --take-over", message)
        self.assertEqual(self.orca.ran("terminal", "create"), [])
        self.assertNotIn("maestro", self.config())

    def test_maestro_un_bail_expire_ne_l_empeche_pas(self):
        ballet_maestro.claim()
        config = self.config()
        config["lease"]["renewed"] = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat(timespec="seconds")
        ballet_maestro.write_config(config)
        self.assertEqual(ballet_maestro.maestro(self.orca), "maestro created: terminal term_1")

    def test_maestro_avec_une_orca_injoignable_ne_cree_rien(self):
        ballet_maestro.write_config({"maestro": {"terminal": "term_1"}})
        self.orca.unreachable = True
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.maestro(self.orca)
        self.assertEqual(self.orca.ran("terminal", "create"), [])

    def test_maestro_dont_la_creation_echoue_ne_note_aucun_terminal(self):
        self.orca.unreachable = True
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.maestro(self.orca)
        self.assertNotIn("maestro", ballet_maestro.read_config())

    def test_maestro_ne_touche_ni_a_la_boite_ni_au_monitor_ni_au_bail(self):
        ballet_maestro.mailbox(self.orca)
        ballet_maestro.monitor(self.orca)
        before = self.config()
        ballet_maestro.maestro(self.orca)
        after = self.config()
        for table in ("mailbox", "monitor", "lease", "projects"):
            self.assertEqual(after[table], before[table], table)
        self.assertEqual(after["maestro"], {"terminal": "term_3"})

    def test_la_ligne_de_commande_maestro(self):
        code, out, _ = self.run_main("maestro")
        self.assertEqual((code, out), (0, "maestro created: terminal term_1\n"))
        self.assertEqual(self.run_main("maestro")[1], "maestro already there: terminal term_1\n")

    def test_project_add_garde_auto_launch_d_un_projet_connu(self):
        folder = self.project("antimurphy")
        ballet_maestro.add_project("antimurphy", str(folder))
        self.trust("antimurphy", "Task")
        ballet_maestro.add_project("antimurphy", str(folder))
        self.assertEqual(self.config()["projects"]["antimurphy"]["auto_launch"], ["Task"])

    # --- la règle de lancement automatique ---

    def trust(self, alias, *types):
        config = ballet_maestro.read_config()
        config["projects"].setdefault(alias, {"path": str(self.root)})["auto_launch"] = list(types)
        ballet_maestro.write_config(config)

    def test_un_type_confie_a_l_auto_est_lance_seul(self):
        self.trust("antimurphy", "Task", "Bug")
        self.assertEqual(ballet_maestro.decision("antimurphy", "Task"), "launch")
        self.assertEqual(ballet_maestro.decision("antimurphy", "Bug"), "launch")

    def test_un_type_non_confie_est_demande_au_director(self):
        self.trust("antimurphy", "Task", "Bug")
        self.assertEqual(ballet_maestro.decision("antimurphy", "Feature"), "ask the Director (Feature is not in auto_launch of antimurphy)")

    def test_par_defaut_rien_n_est_confie_a_l_auto(self):
        ballet_maestro.add_project("antimurphy", str(self.project("antimurphy")))
        self.assertIn("ask the Director", ballet_maestro.decision("antimurphy", "Task"))

    def test_un_element_dont_le_conductor_a_disparu_est_demande_au_director(self):
        self.trust("antimurphy", "Feature")
        ballet_conductors.record_launch("antimurphy#49", "antimurphy", "#49", "rehearsal", "term_7")
        ballet_conductors.mark_gone("antimurphy#49", "term_7")
        self.assertIn("its last Conductor is gone", ballet_maestro.decision("antimurphy", "Feature", number="49"))
        self.assertEqual(ballet_maestro.decision("antimurphy", "Feature", number="50"), "launch")

    def test_un_element_relance_par_le_director_retrouve_la_regle(self):
        self.trust("antimurphy", "Feature")
        ballet_conductors.record_launch("antimurphy#49", "antimurphy", "#49", "rehearsal", "term_7")
        ballet_conductors.mark_gone("antimurphy#49", "term_7")
        ballet_conductors.record_launch("antimurphy#49", "antimurphy", "#49", "rehearsal", "term_8")
        self.assertEqual(ballet_maestro.decision("antimurphy", "Feature", number="49"), "launch")

    def test_la_confiance_est_par_projet(self):
        self.trust("antimurphy", "Task")
        self.trust("beta")
        self.assertEqual(ballet_maestro.decision("antimurphy", "Task"), "launch")
        self.assertIn("ask the Director", ballet_maestro.decision("beta", "Task"))

    def test_la_pause_arrete_tout_lancement_seul(self):
        self.trust("antimurphy", "Task")
        ballet_maestro.pause()
        self.assertEqual(ballet_maestro.decision("antimurphy", "Task"), "ask the Director (auto launch is paused)")
        ballet_maestro.resume()
        self.assertEqual(ballet_maestro.decision("antimurphy", "Task"), "launch")

    def test_un_projet_inconnu_ou_une_liste_mal_ecrite_se_demande(self):
        self.assertEqual(ballet_maestro.decision("ghost", "Task"), "ask the Director (unknown project ghost)")
        config = ballet_maestro.read_config()
        config["projects"]["antimurphy"] = {"path": str(self.root), "auto_launch": "Task"}
        ballet_maestro.write_config(config)
        self.assertIn("auto_launch must be a list", ballet_maestro.decision("antimurphy", "Task"))

    # --- pause, resume ---

    def test_pause_pose_le_drapeau_dans_le_dossier_d_etat_et_resume_le_retire(self):
        flag = self.state / "auto_launch_paused"
        self.assertIn("paused", ballet_maestro.pause())
        self.assertTrue(flag.is_file())
        self.assertIn("resumed", ballet_maestro.resume())
        self.assertFalse(flag.exists())

    def test_pause_et_resume_se_rejouent_sans_erreur(self):
        ballet_maestro.pause()
        self.assertEqual(ballet_maestro.pause(), "auto launch was already paused")
        ballet_maestro.resume()
        self.assertEqual(ballet_maestro.resume(), "auto launch was not paused")

    def test_pause_ne_perd_pas_l_etat_de_maestro(self):
        self.trust("antimurphy", "Task")
        ballet_maestro.pause()
        self.assertEqual(self.config()["projects"]["antimurphy"]["auto_launch"], ["Task"])

    # --- les messages ready de wait et de recap ---

    def ready_message(self, number=12, kind="Task", subject=None, project="antimurphy"):
        return self.message(subject=subject or f"{project}#{number} · ready", sender="term_5", priority="normal",
                            body=f"#{number} · {kind} · High · Le panier se vide · https://github.com/acme/shop/issues/{number}")

    def test_wait_ecrit_la_decision_sous_un_element_ready(self):
        owner = self.claimed()
        self.trust("antimurphy", "Task")
        self.orca.batches = [[self.ready_message(12, "Task"), self.ready_message(13, "Feature")]]
        output = ballet_maestro.wait(owner, self.orca)
        self.assertIn("· Task · High · Le panier se vide · https://github.com/acme/shop/issues/12\nDECISION: launch", output)
        self.assertIn("issues/13\nDECISION: ask the Director (Feature is not in auto_launch of antimurphy)", output)

    def test_wait_dit_la_pause_dans_la_decision(self):
        owner = self.claimed()
        self.trust("antimurphy", "Task")
        ballet_maestro.pause()
        self.orca.batches = [[self.ready_message()]]
        self.assertIn("DECISION: ask the Director (auto launch is paused)", ballet_maestro.wait(owner, self.orca))

    def test_un_message_groupe_a_une_decision_par_element(self):
        owner = self.claimed()
        self.trust("antimurphy", "Bug")
        body = "#3 · Bug · Urgent · Un bug · https://x/3\n#4 · Task · no priority · Une tâche · https://x/4"
        self.orca.batches = [[{**self.ready_message(subject="antimurphy · ready (2 already)"), "body": body}]]
        output = ballet_maestro.wait(owner, self.orca)
        self.assertIn("https://x/3\nDECISION: launch\n#4", output)
        self.assertIn("https://x/4\nDECISION: ask the Director (Task is not in auto_launch of antimurphy)", output)

    def test_les_autres_messages_n_ont_pas_de_decision(self):
        owner = self.claimed()
        self.orca.batches = [[self.message(), self.message(subject="antimurphy#12 · gone", body="#12 · Task · x")]]
        self.assertNotIn("DECISION", ballet_maestro.wait(owner, self.orca))

    def test_recap_ecrit_aussi_la_decision_et_ne_note_pas_le_monitor_comme_un_conductor(self):
        owner = self.claimed()
        self.trust("antimurphy", "Task")
        self.orca.batches = [[{**self.ready_message(), "id": "msg_9"}]]
        self.orca.history = [self.row(1, subject="antimurphy#12 · ready", body="#12 · Task · High · T · https://x/12")]
        self.assertIn("DECISION: launch", ballet_maestro.recap(owner, self.orca))
        self.assertEqual(ballet_conductors.read(), {})

    def test_wait_ne_note_pas_un_ready_ni_un_gone_comme_un_conductor(self):
        owner = self.claimed()
        self.orca.batches = [[self.ready_message(), self.message(subject="antimurphy#12 · gone", sender="term_5")]]
        ballet_maestro.wait(owner, self.orca)
        self.assertEqual(ballet_conductors.read(), {})

    # --- ready ---

    def seen_ready(self, alias, *items):
        """Ce que le Monitor a vu prêt dans un projet, dans l'ordre de la file : (numéro, type, priorité, titre)."""
        document = json.loads((self.state / "monitor.json").read_text(encoding="utf-8")) if (self.state / "monitor.json").exists() else {"projects": {}}
        document["projects"][alias] = {"ready": [
            {"item": f"#{number}", "number": number, "type": kind, "priority": priority, "title": title, "url": f"https://x/{number}"}
            for number, kind, priority, title in items]}
        self.state.mkdir(exist_ok=True)
        (self.state / "monitor.json").write_text(json.dumps(document), encoding="utf-8")

    def test_ready_liste_les_elements_prets_dans_l_ordre_de_la_file_avec_leur_decision(self):
        self.trust("antimurphy", "Task")
        self.seen_ready("antimurphy", (7, "Task", "Urgent", "Le premier"), (3, "Feature", "", "Le second"))
        lines = ballet_maestro.ready().splitlines()
        self.assertEqual(lines[0], "antimurphy#7  Task  Urgent  Le premier  https://x/7  DECISION: launch")
        self.assertEqual(lines[1], "antimurphy#3  Feature  -  Le second  https://x/3  DECISION: ask the Director (Feature is not in auto_launch of antimurphy)")

    def seen_with_dependencies(self, alias, number, blocked_by=(), doubt=""):
        """Ce que le Monitor a vu des dépendances d'un élément déjà noté prêt."""
        document = json.loads((self.state / "monitor.json").read_text(encoding="utf-8"))
        for item in document["projects"][alias]["ready"]:
            if item["number"] == number:
                item["blocked_by"] = [{"item": f"#{found}", "number": found, "repo": "acme/shop", "url": f"https://x/{found}"} for found in blocked_by]
                item["doubt"] = doubt
        (self.state / "monitor.json").write_text(json.dumps(document), encoding="utf-8")

    def test_ready_montre_un_element_bloque_avec_wait_meme_pour_un_type_confie_a_l_auto(self):
        self.trust("antimurphy", "Task")
        self.seen_ready("antimurphy", (7, "Task", "", "Bloqué"), (8, "Task", "", "Libre"))
        self.seen_with_dependencies("antimurphy", 7, blocked_by=(3, 5))
        lines = ballet_maestro.ready().splitlines()
        self.assertEqual(lines[0], "antimurphy#7  Task  -  Bloqué  https://x/7  DECISION: wait (blocked by #3, #5, open)")
        self.assertTrue(lines[1].endswith("DECISION: launch"))

    def test_un_bloqueur_d_un_autre_repo_est_nomme_avec_son_repo_dans_wait(self):
        self.trust("antimurphy")
        self.seen_ready("antimurphy", (7, "Task", "", "Bloqué"))
        document = json.loads((self.state / "monitor.json").read_text(encoding="utf-8"))
        document["projects"]["antimurphy"]["ready"][0]["blocked_by"] = [{"item": "acme/api#5", "number": 5, "repo": "acme/api", "url": "https://x/5"}]
        (self.state / "monitor.json").write_text(json.dumps(document), encoding="utf-8")
        self.assertIn("DECISION: wait (blocked by acme/api#5, open)", ballet_maestro.ready())

    def test_un_doute_de_dependance_demande_au_director_meme_pour_un_type_confie_a_l_auto(self):
        self.trust("antimurphy", "Task")
        self.seen_ready("antimurphy", (7, "Task", "", "Douteux"))
        self.seen_with_dependencies("antimurphy", 7, doubt="blocker #3 was closed as not planned, not delivered")
        self.assertTrue(ballet_maestro.ready().endswith(
            "DECISION: ask the Director (blocker #3 was closed as not planned, not delivered)"))

    def test_un_cycle_demande_au_director_et_non_wait(self):
        self.trust("antimurphy")
        self.seen_ready("antimurphy", (7, "Task", "", "En cycle"))
        self.seen_with_dependencies("antimurphy", 7, blocked_by=(8,), doubt="dependency cycle: #7 → #8 → #7")
        self.assertTrue(ballet_maestro.ready().endswith("DECISION: ask the Director (dependency cycle: #7 → #8 → #7)"))

    def test_status_montre_aussi_les_elements_bloques(self):
        self.trust("antimurphy")
        self.seen_ready("antimurphy", (7, "Task", "", "Bloqué"))
        self.seen_with_dependencies("antimurphy", 7, blocked_by=(3,))
        self.assertIn("Ready, no Conductor yet:\nantimurphy#7  Task  -  Bloqué  https://x/7  DECISION: wait (blocked by #3, open)",
                      ballet_maestro.status(self.orca))

    def test_la_decision_sous_un_message_ready_suit_l_etat_que_le_monitor_a_garde(self):
        owner = self.claimed()
        self.trust("antimurphy", "Task")
        self.seen_ready("antimurphy", (12, "Task", "High", "Le panier se vide"))
        self.orca.batches = [[self.ready_message()], [self.ready_message()]]
        self.assertIn("DECISION: launch", ballet_maestro.wait(owner, self.orca))
        self.seen_with_dependencies("antimurphy", 12, blocked_by=(3,))
        self.assertIn("DECISION: wait (blocked by #3, open)", ballet_maestro.wait(owner, self.orca))

    def test_ready_relit_les_bloqueurs_sur_github_qu_un_done_vient_de_fermer(self):
        self.trust("antimurphy", "Task")
        self.seen_ready("antimurphy", (7, "Task", "", "Bloqué"))
        self.seen_with_dependencies("antimurphy", 7, blocked_by=(3,))
        self.live = [{"number": 7, "blocked_by": [], "launchable": True, "doubt": ""}]
        self.assertTrue(ballet_maestro.ready().endswith("DECISION: launch"))
        self.assertEqual(len(self.live_reads), 1)

    def test_ready_garde_la_vue_du_monitor_quand_github_ne_repond_pas(self):
        self.trust("antimurphy", "Task")
        self.seen_ready("antimurphy", (7, "Task", "", "Bloqué"))
        self.seen_with_dependencies("antimurphy", 7, blocked_by=(3,))
        self.assertTrue(ballet_maestro.ready().endswith("DECISION: wait (blocked by #3, open)"))

    def test_ready_ne_relit_rien_sans_element_bloque(self):
        self.trust("antimurphy", "Task")
        self.seen_ready("antimurphy", (7, "Task", "", "Libre"))
        ballet_maestro.ready()
        self.assertEqual(self.live_reads, [])

    def finished_message(self, key="antimurphy#12", terminal="term_9"):
        return {"type": "status", "subject": f"{key} · finished", "from": "term_monitor",
                "body": f"The rehearsal Conductor of {key} finished at x and its terminal {terminal} is still open after 10 min. "
                        f"Close it with: ballet_launch.py close {key}"}

    def test_un_conductor_fini_signale_se_ferme_quand_rien_n_a_change(self):
        owner = self.claimed()
        ballet_conductors.record_launch("antimurphy#12", "antimurphy", "12", "rehearsal", "term_9")
        ballet_conductors.note_events([{"type": "status", "from": "term_9", "subject": "antimurphy#12 · done"}])
        self.orca.batches = [[self.finished_message()]]
        self.assertIn("ballet_launch.py close antimurphy#12\nDECISION: close", ballet_maestro.wait(owner, self.orca))

    def test_un_conductor_relance_depuis_n_est_pas_ferme_sans_le_director(self):
        ballet_conductors.record_launch("antimurphy#12", "antimurphy", "12", "rehearsal", "term_9")
        self.assertEqual(ballet_maestro.close_decision("antimurphy#12", "term_9"),
                         "ask the Director (antimurphy#12 is running now, not finished)")
        ballet_conductors.note_events([{"type": "status", "from": "term_4", "subject": "antimurphy#12 · done"}])
        self.assertEqual(ballet_maestro.close_decision("antimurphy#12", "term_9"),
                         "ask the Director (antimurphy#12 now runs in term_4, not term_9)")

    def test_un_conductor_que_maestro_n_a_pas_lance_n_est_pas_ferme_sans_le_director(self):
        ballet_conductors.note_events([{"type": "status", "from": "term_9", "subject": "antimurphy#12 · done"}])
        self.assertTrue(ballet_maestro.close_decision("antimurphy#12", "term_9").startswith("ask the Director (Maestro did not launch"))

    def test_le_delai_de_fermeture_est_un_entier_positif_ou_nul(self):
        self.assertEqual(ballet_maestro.close_delay_minutes({}), 10)
        self.assertEqual(ballet_maestro.close_delay_minutes({"conductors": {"close_finished_after_minutes": 0}}), 0)
        for wrong in (-1, "10", True, 2.5):
            with self.subTest(value=wrong), self.assertRaises(ballet_maestro.MaestroError):
                ballet_maestro.close_delay_minutes({"conductors": {"close_finished_after_minutes": wrong}})

    def test_ready_ne_montre_pas_un_element_qu_un_conductor_joue(self):
        self.trust("antimurphy", "Task")
        self.seen_ready("antimurphy", (7, "Task", "", "Joué"), (8, "Task", "", "Attend"))
        ballet_conductors.record_launch("antimurphy#7", "antimurphy", "7", "rehearsal", "term_9")
        self.assertEqual([line.split()[0] for line in ballet_maestro.ready().splitlines()], ["antimurphy#8"])

    def test_ready_remontre_un_element_dont_le_conductor_a_disparu(self):
        self.trust("antimurphy", "Task")
        self.seen_ready("antimurphy", (7, "Task", "", "Revenu"))
        ballet_conductors.record_launch("antimurphy#7", "antimurphy", "7", "rehearsal", "term_9")
        self.assertTrue(ballet_conductors.mark_gone("antimurphy#7", "term_9"))
        self.assertTrue(ballet_maestro.ready().startswith("antimurphy#7"))

    def test_ready_sans_element_en_attente_le_dit(self):
        self.assertIn("no item is waiting", ballet_maestro.ready())

    def test_ready_ignore_un_projet_que_maestro_ne_connait_plus(self):
        self.seen_ready("oublie", (1, "Task", "", "x"))
        self.assertIn("no item is waiting", ballet_maestro.ready())

    def test_status_montre_aussi_les_elements_prets_sans_conductor(self):
        self.trust("antimurphy", "Task")
        self.seen_ready("antimurphy", (7, "Task", "", "Le premier"))
        self.assertIn("Ready, no Conductor yet:\nantimurphy#7  Task", ballet_maestro.status(self.orca))

    def test_la_ligne_de_commande_ready_pause_resume_et_monitor(self):
        self.assertEqual(self.run_main("monitor")[:2], (0, "monitor created: terminal term_1\n"))
        self.assertEqual(self.run_main("pause")[0], 0)
        self.assertTrue((self.state / "auto_launch_paused").is_file())
        self.assertEqual(self.run_main("resume")[0], 0)
        self.assertFalse((self.state / "auto_launch_paused").exists())
        self.assertIn("no item is waiting", self.run_main("ready")[1])

    # --- ligne de commande ---

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ballet_maestro.main(["ballet_maestro.py", *argv], orca=self.orca)
        return code, out.getvalue(), err.getvalue()

    def test_la_ligne_de_commande_cree_la_boite_puis_la_retrouve(self):
        self.assertEqual(self.run_main("mailbox")[:2], (0, "mailbox created: terminal term_1, run:run_1\n"))
        self.assertEqual(self.run_main("mailbox")[:2], (0, "mailbox already there: terminal term_1, run:run_1\n"))

    def test_un_usage_invalide_sort_avec_deux(self):
        code, _, err = self.run_main("project", "add", "antimurphy")
        self.assertEqual(code, 2)
        self.assertIn("usage:", err)

    def test_la_ligne_de_commande_prend_le_bail_puis_le_refuse_au_second(self):
        code, out, _ = self.run_main("claim")
        self.assertEqual((code, out.startswith("lease claimed, owner ")), (0, True))
        code, _, err = self.run_main("claim")
        self.assertEqual(code, 1)
        self.assertIn("--take-over", err)
        self.waiting(running=False)
        self.assertEqual(self.run_main("claim", "--take-over")[0], 0)

    def test_la_ligne_de_commande_tell_joint_les_mots_de_la_reponse(self):
        self.known_conductor()
        self.orca.terminals.append("term_9")
        self.assertEqual(self.run_main("tell", "antimurphy#12", "yes", "go")[0], 0)
        send = self.orca.ran("terminal", "send")[0]
        self.assertEqual(send[send.index("--text") + 1], "Director answers: yes go")

    def test_un_wait_sans_jeton_est_un_usage_invalide(self):
        self.assertEqual(self.run_main("wait")[0], 2)

    def test_un_refus_sort_avec_un_et_le_dit(self):
        self.orca.unreachable = True
        code, _, err = self.run_main("mailbox")
        self.assertEqual(code, 1)
        self.assertIn("could not connect to Orca", err)


if __name__ == "__main__":
    unittest.main()
