import io
import json
import sys
import tempfile
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

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

    def config(self):
        return tomllib.loads((self.state / "maestro.toml").read_text(encoding="utf-8"))

    def project(self, name):
        folder = self.root / name
        folder.mkdir()
        return folder

    # --- maestro.toml ---

    def test_le_toml_ecrit_se_relit_a_l_identique(self):
        config = {"mailbox": {"terminal": "term_1", "run": "run_1"}, "lease": {"owner": "abc", "pid": 4242, "renewed": "2026-11-21T08:00:00+00:00"},
                  "projects": {"antimurphy": {"path": "/p/antimurphy"}, "mon projet": {"path": "/p/\"quoted\" été\n"}},
                  "limits": {"auto_launch": ["Task", "Bug"], "paused": False}}
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
        registry = ballet_maestro.read_conductors()
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

    def test_recap_montre_le_non_lu_et_l_historique_du_plus_ancien_au_plus_recent(self):
        ballet_maestro.mailbox(self.orca)
        self.orca.history = [self.row(3, read=0, subject="am#3 · done"), self.row(2, subject="am#2 · escalate"), self.row(1, subject="am#1 · done")]
        output = ballet_maestro.recap(self.orca)
        self.assertLess(output.index("am#1"), output.index("am#2"))
        self.assertLess(output.index("am#2"), output.index("am#3"))
        self.assertIn("3 message(s), 1 unread", output)
        self.assertIn("· unread\nSubject: am#3 · done", output)
        self.assertIn("· read\nSubject: am#1 · done", output)

    def test_recap_ne_consomme_rien(self):
        ballet_maestro.mailbox(self.orca)
        self.orca.history = [self.row(1, read=0)]
        ballet_maestro.recap(self.orca)
        self.assertEqual(self.orca.ran("orchestration", "check"), [])
        inbox = self.orca.ran("orchestration", "inbox")[0]
        self.assertEqual(inbox[inbox.index("--terminal") + 1], "run:run_1")
        self.assertIn("--full", inbox)

    def test_recap_ne_garde_que_les_derniers_messages(self):
        ballet_maestro.mailbox(self.orca)
        self.orca.history = [self.row(number, subject=f"am#{number} · done") for number in range(30, 0, -1)]
        output = ballet_maestro.recap(self.orca)
        self.assertIn("10 message(s)", output)
        self.assertIn("am#30 · done", output)
        self.assertNotIn("am#20 · done", output)

    def test_recap_relit_la_run_precedente_puis_l_oublie(self):
        ballet_maestro.mailbox(self.orca)
        config = ballet_maestro.read_config()
        config["mailbox"]["previous_run"] = "run_0"
        ballet_maestro.write_config(config)
        self.orca.history = [self.row(2, subject="am#2 · done"), self.row(1, run="run_0", subject="old#1 · escalate")]
        output = ballet_maestro.recap(self.orca)
        self.assertIn("old#1 · escalate", output)
        self.assertNotIn("previous_run", self.config()["mailbox"])
        self.assertNotIn("old#1", ballet_maestro.recap(self.orca))

    def test_recap_d_une_boite_vide_le_dit(self):
        ballet_maestro.mailbox(self.orca)
        self.assertEqual(ballet_maestro.recap(self.orca), "the mailbox is empty")

    def test_recap_sans_boite_dit_de_la_creer(self):
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.recap(self.orca)

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
        lines = ballet_maestro.status().splitlines()
        self.assertEqual(lines, ["antimurphy  #12  FEAT-004.1  escalated  term_9",
                                 "antimurphy  FEAT-005  -  open  no terminal known"])

    def test_status_montre_aussi_les_workshops_ouverts_et_ignore_les_sessions_finies(self):
        import ballet_rehearsal
        folder = self.project("antimurphy")
        ballet_maestro.add_project("antimurphy", str(folder))
        ballet_rehearsal._save_session(Session(item="#3", status="done"), folder)
        run = folder / ".ballet" / "run"
        (run / "workshop-OPP-12.json").write_text(json.dumps({"item": "OPP-12", "repo": "r", "status": "escalated"}), encoding="utf-8")
        (run / "workshop-OPP-13.json").write_text(json.dumps({"item": "OPP-13", "repo": "r", "status": "done"}), encoding="utf-8")
        self.assertEqual(ballet_maestro.status(), "antimurphy  OPP-12  Workshop  escalated  no terminal known")

    def test_status_sans_session_ni_dossier_run_le_dit_et_ne_cree_rien(self):
        folder = self.project("antimurphy")
        ballet_maestro.add_project("antimurphy", str(folder))
        self.assertEqual(ballet_maestro.status(), "no open session in any project")
        self.assertFalse((folder / ".ballet").exists())

    def test_status_parcourt_chaque_projet(self):
        for name, item in (("beta", "#2"), ("alpha", "#1")):
            folder = self.project(name)
            ballet_maestro.add_project(name, str(folder))
            self.open_session(folder, item)
        self.assertEqual([line.split()[0] for line in ballet_maestro.status().splitlines()], ["alpha", "beta"])

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
