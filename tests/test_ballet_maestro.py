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
import ballet_monitor  # noqa: E402
import ballet_runtime  # noqa: E402
import ballet_session  # noqa: E402
import ballet_store  # noqa: E402
from ballet_rehearsal import Rehearsal, Session, Step  # noqa: E402
from ballet_workshop import Workshop  # noqa: E402


LEAN_OPTIONS = ("--strict-mcp-config --mcp-config '{\"mcpServers\":{}}' --tools Bash,Read,Skill "
                + shlex.join(ballet_session.statusline_options()))   # le socle allégé, puis la statusline de la sonde de capacité
EMPTY_LEASE = {"owner": "", "pid": 0, "renewed": "", "session": ""}


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
        path = self.state / "maestro.toml"
        return tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    def runtime(self):
        return ballet_runtime.read()

    def lease(self):
        runtime = self.runtime()
        return {"owner": runtime["lease_owner"], "pid": runtime["lease_pid"], "renewed": runtime["lease_renewed_at"],
                "session": runtime["lease_session"]}

    def box(self):
        """La boîte notée : terminal, Run, Run d'avant, sans les valeurs vides."""
        runtime = self.runtime()
        found = {"terminal": runtime["mailbox_terminal"], "run": runtime["mailbox_run"], "previous_run": runtime["mailbox_previous_run"]}
        return {key: value for key, value in found.items() if value}

    def project(self, name):
        folder = self.root / name
        folder.mkdir()
        return folder

    # --- maestro.toml ---

    def test_le_toml_ecrit_se_relit_a_l_identique(self):
        config = {"maestro": {"restart_at_context_percent": 20},
                  "projects": {"antimurphy": {"path": "/p/antimurphy", "auto_launch": ["Task", "Bug"]},
                               "mon projet": {"path": "/p/\"quoted\" été\n"}},
                  "limits": {"max_running": 3}}
        ballet_maestro.write_config(config)
        self.assertEqual(self.config(), config)

    def test_le_toml_ne_garde_que_la_config(self):
        ballet_maestro.add_project("antimurphy", str(self.project("antimurphy")))
        ballet_maestro.mailbox(self.orca)
        ballet_maestro.claim()
        self.assertEqual(sorted(self.config()), ["projects"])

    def test_sans_fichier_la_config_et_l_etat_sont_vides(self):
        self.assertEqual(ballet_maestro.read_config(), {"projects": {}})
        self.assertEqual(self.lease(), EMPTY_LEASE)
        self.assertEqual(self.box(), {})

    def test_une_ecriture_interrompue_laisse_l_ancien_fichier_entier_et_aucun_temporaire(self):
        ballet_maestro.write_config({"projects": {"old": {"path": "/old"}}})
        with mock.patch.object(ballet_maestro, "to_toml", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            ballet_maestro.write_config({"projects": {"new": {"path": "/new"}}})
        self.assertEqual(self.config()["projects"], {"old": {"path": "/old"}})
        self.assertEqual(sorted(path.name for path in self.state.iterdir()), ["maestro.toml"])

    def test_l_ecriture_remplace_le_fichier_par_un_renommage(self):
        with mock.patch.object(ballet_maestro.os, "replace", wraps=ballet_maestro.os.replace) as replace:
            ballet_maestro.write_config({"projects": {}})
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
        self.assertEqual(self.box(), {"terminal": "term_1", "run": "run_1"})

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
        self.assertEqual(self.box(), {"terminal": "term_2", "run": "run_2", "previous_run": "run_1"})

    def test_une_orca_injoignable_ne_cree_rien(self):
        ballet_runtime.update(mailbox_terminal="term_1", mailbox_run="run_1")
        self.orca.unreachable = True
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.mailbox(self.orca)
        self.assertEqual(self.orca.ran("terminal", "create"), [])
        self.assertEqual(self.box(), {"terminal": "term_1", "run": "run_1"})

    def test_une_run_qui_echoue_garde_le_terminal_et_l_appel_suivant_ne_cree_que_la_run(self):
        self.orca.run_failures = 1
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.mailbox(self.orca)
        self.assertEqual(self.box(), {"terminal": "term_1"})
        self.assertEqual(ballet_maestro.mailbox(self.orca), "mailbox created: terminal term_1, run:run_1")
        self.assertEqual(len(self.orca.ran("terminal", "create")), 1)

    def test_mailbox_garde_les_projets_et_le_bail(self):
        ballet_maestro.add_project("antimurphy", str(self.project("antimurphy")))
        ballet_maestro.mailbox(self.orca)
        self.assertIn("antimurphy", self.config()["projects"])
        self.assertEqual(self.lease(), EMPTY_LEASE)

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
        ballet_maestro.write_config({"projects": {"am": {"path": str(folder)}}})
        ballet_runtime.update(mailbox_run="run_box")
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
        ballet_runtime.update(mailbox_run="run_box")
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
        ballet_runtime.update(mailbox_run="run_box")
        for step in (Step("wait", item="#12"), Step("escalate", "a read")):
            ballet_maestro.announce(step, self.root, self.orca)
        self.assertEqual(self.orca.commands, [])

    # --- le bail ---

    def hold_lease(self, owner="other", pid=0, age=timedelta(0)):
        """Le bail d'une autre session, renouvelé il y a `age`."""
        renewed = (datetime.now(timezone.utc) - age).isoformat(timespec="seconds")
        ballet_runtime.update(lease_owner=owner, lease_pid=pid, lease_renewed_at=renewed)

    def waiting(self, running=True):
        """`ps` voit (ou non) une attente de Maestro tourner sous un pid."""
        patch = mock.patch.object(ballet_maestro, "_wait_runs", return_value=running)
        patch.start()
        self.addCleanup(patch.stop)

    def test_claim_libre_ecrit_un_jeton_et_l_affiche(self):
        output = ballet_maestro.claim()
        lease = self.lease()
        self.assertEqual(output, f"lease claimed, owner {lease['owner']}")
        self.assertRegex(lease["owner"], r"^[0-9a-f]{16}$")
        self.assertEqual(lease["pid"], 0)
        self.assertTrue(lease["renewed"])

    def test_claim_refuse_un_bail_renouvele_il_y_a_moins_de_dix_minutes_et_propose_take_over(self):
        self.hold_lease(age=timedelta(minutes=9))
        with self.assertRaises(ballet_maestro.MaestroError) as refused:
            ballet_maestro.claim()
        self.assertIn("claim --take-over", str(refused.exception))
        self.assertEqual(self.lease()["owner"], "other")

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
        self.assertNotEqual(self.lease()["owner"], "other")

    def test_claim_prend_un_bail_sans_proprietaire(self):
        ballet_maestro.claim()
        self.assertTrue(self.lease()["owner"])

    def test_take_over_arrete_l_attente_de_l_ancien_puis_prend_le_bail(self):
        self.hold_lease(pid=4242, age=timedelta(minutes=1))
        self.waiting(running=True)
        with mock.patch.object(ballet_maestro.os, "kill") as kill:
            ballet_maestro.claim(take_over=True)
        kill.assert_called_once_with(4242, ballet_maestro.signal.SIGTERM)
        lease = self.lease()
        self.assertNotEqual(lease["owner"], "other")
        self.assertEqual(lease["pid"], 0)

    def test_take_over_sans_attente_vivante_ne_tue_rien(self):
        self.hold_lease(pid=4242, age=timedelta(minutes=1))
        self.waiting(running=False)
        with mock.patch.object(ballet_maestro.os, "kill") as kill:
            ballet_maestro.claim(take_over=True)
        kill.assert_not_called()
        self.assertNotEqual(self.lease()["owner"], "other")

    def test_deux_claims_tour_a_tour_le_second_est_refuse(self):
        ballet_maestro.claim()
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.claim()

    def test_claim_note_l_id_de_session_claude_dans_le_bail(self):
        with mock.patch.dict("os.environ", {"CLAUDE_CODE_SESSION_ID": "5d5057ed-f4f9"}):
            ballet_maestro.claim()
        self.assertEqual(self.lease()["session"], "5d5057ed-f4f9")

    def test_claim_hors_de_claude_laisse_la_session_vide(self):
        with mock.patch.dict("os.environ", clear=False) as environment:
            environment.pop("CLAUDE_CODE_SESSION_ID", None)
            ballet_maestro.claim()
        self.assertEqual(self.lease()["session"], "")

    def test_take_over_note_la_session_de_la_nouvelle_proprietaire(self):
        with mock.patch.dict("os.environ", {"CLAUDE_CODE_SESSION_ID": "ancienne"}):
            ballet_maestro.claim()
        with mock.patch.dict("os.environ", {"CLAUDE_CODE_SESSION_ID": "nouvelle"}):
            ballet_maestro.claim(take_over=True)
        self.assertEqual(self.lease()["session"], "nouvelle")

    def test_lever_le_bail_efface_la_session(self):
        with mock.patch.dict("os.environ", {"CLAUDE_CODE_SESSION_ID": "ancienne"}):
            ballet_maestro.claim()
        ballet_maestro.release_lease()
        self.assertEqual(self.lease(), EMPTY_LEASE)

    def test_une_attente_garde_la_session_du_bail(self):
        ballet_maestro.mailbox(self.orca)
        with mock.patch.dict("os.environ", {"CLAUDE_CODE_SESSION_ID": "s-1"}):
            owner = ballet_maestro.claim().rsplit(" ", 1)[1]
        self.orca.batches = [[self.message()]]
        ballet_maestro.wait(owner, self.orca)
        self.assertEqual(self.lease()["session"], "s-1")

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
                seen.update(self.lease())
            return original(arguments)
        self.orca.batches = [[self.message()]]
        ballet_maestro.wait(owner, spying)
        self.assertEqual(seen["pid"], ballet_maestro.os.getpid())
        lease = self.lease()
        self.assertEqual((lease["owner"], lease["pid"]), (owner, 0))
        self.assertGreaterEqual(lease["renewed"], seen["renewed"])

    def test_wait_remet_le_pid_a_zero_meme_quand_orca_tombe(self):
        owner = self.claimed()
        self.orca.unreachable = True
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.wait(owner, self.orca)
        self.assertEqual(self.lease()["pid"], 0)

    def test_wait_arrete_par_un_take_over_ne_touche_pas_au_nouveau_bail(self):
        owner = self.claimed()

        def taken_over(arguments):
            if arguments[:2] == ["orchestration", "check"]:
                self.hold_lease(owner="new-owner", pid=0)
                raise ballet_maestro.MaestroError("stopped")
            return self.orca(arguments)
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.wait(owner, taken_over)
        self.assertEqual(self.lease()["owner"], "new-owner")

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
        registry = ballet_conductors.read()
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
        self.assertEqual(ballet_conductors.read(), {})

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
        ballet_runtime.update(mailbox_previous_run="run_0")
        self.orca.history = [self.row(2, subject="am#2 · done"), self.row(1, run="run_0", subject="old#1 · escalate")]
        output = ballet_maestro.recap(owner, self.orca)
        self.assertIn("old#1 · escalate", output)
        self.assertNotIn("previous_run", self.box())
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
        self.known_conductor()
        lines = ballet_maestro.status(self.orca).splitlines()
        self.assertEqual(lines[:2], ["antimurphy  #12  FEAT-004.1  escalated  term_9",
                                     "antimurphy  FEAT-005  -  open  no terminal known"])

    def test_status_montre_aussi_les_workshops_ouverts_et_ignore_les_sessions_finies(self):
        import ballet_rehearsal
        folder = self.project("antimurphy")
        ballet_maestro.add_project("antimurphy", str(folder))
        ballet_rehearsal._save_session(Session(item="#3", status="done"), folder)
        ballet_store.save(folder, "workshop", {"item": "OPP-12", "repo": "r", "status": "escalated"})
        ballet_store.save(folder, "workshop", {"item": "OPP-13", "repo": "r", "status": "done"})
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
        """Un Conductor que Maestro n'a pas lancé, connu par son escalade."""
        ballet_conductors.note_events([{"type": "status", "subject": "antimurphy#12 · escalate", "from": handle}])

    def test_tell_ecrit_la_reponse_du_director_dans_le_terminal_du_conductor(self):
        self.known_conductor()
        self.orca.terminals.append("term_9")
        self.assertEqual(ballet_maestro.tell("antimurphy#12", "approve the plan", self.orca), "told antimurphy#12 (terminal term_9)")
        send = self.orca.ran("terminal", "send")[0]
        self.assertEqual(send[send.index("--terminal") + 1], "term_9")
        self.assertEqual(send[send.index("--text") + 1], "Director answers: approve the plan")
        self.assertIn("--enter", send)

    def test_tell_override_ecrit_la_raison_du_director_sous_son_propre_prefixe(self):
        self.known_conductor()
        self.orca.terminals.append("term_9")
        self.assertEqual(ballet_maestro.tell("antimurphy#12", "the limit is lifted", self.orca, override=True),
                         "told antimurphy#12 (terminal term_9)")
        send = self.orca.ran("terminal", "send")[0]
        self.assertEqual(send[send.index("--text") + 1], "Director overrides: the limit is lifted")

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
        self.assertEqual(self.runtime()["monitor_terminal"], "term_1")

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
        ballet_runtime.update(monitor_terminal="term_1")
        self.orca.unreachable = True
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.monitor(self.orca)
        self.assertEqual(self.orca.ran("terminal", "create"), [])

    def test_monitor_ne_touche_ni_a_la_boite_ni_aux_projets(self):
        ballet_maestro.mailbox(self.orca)
        ballet_maestro.add_project("antimurphy", str(self.project("antimurphy")))
        ballet_maestro.monitor(self.orca)
        self.assertEqual((self.box(), sorted(self.config()["projects"])), ({"terminal": "term_1", "run": "run_1"}, ["antimurphy"]))
        self.assertEqual(self.runtime()["monitor_terminal"], "term_2")

    # --- maestro (la session elle-même) ---

    def test_maestro_cree_le_terminal_de_la_session_avec_sa_commande_et_le_note(self):
        with mock.patch.dict("os.environ", clear=False) as environment:
            environment.pop("BALLET_MAESTRO_COMMAND", None)
            self.assertEqual(ballet_maestro.maestro(self.orca), "maestro created: terminal term_1")
        create = self.orca.ran("terminal", "create")[0]
        self.assertEqual(create[create.index("--title") + 1], "maestro")
        self.assertEqual(create[create.index("--command") + 1],
                         f"BALLET_HOME={self.state} CLAUDE_CODE_PROMPT_CACHE_TTL=1h claude --remote-control 'ballet maestro' /ballet:maestro "
                         f"--model sonnet {LEAN_OPTIONS}")
        self.assertEqual(self.runtime()["maestro_terminal"], "term_1")

    def test_maestro_sans_ballet_home_ne_transmet_rien(self):
        with mock.patch.dict("os.environ", clear=False) as environment:
            environment.pop("BALLET_HOME")
            environment.pop("BALLET_MAESTRO_COMMAND", None)
            self.assertEqual(ballet_maestro._maestro_command(),
                             f"CLAUDE_CODE_PROMPT_CACHE_TTL=1h claude --remote-control 'ballet maestro' /ballet:maestro --model sonnet {LEAN_OPTIONS}")

    def test_maestro_le_prompt_vient_avant_toute_option(self):
        with mock.patch.dict("os.environ", {"BALLET_MAESTRO_COMMAND": "echo fake-maestro"}):
            words = shlex.split(ballet_maestro._maestro_command())
        self.assertEqual(words[2:7], ["echo", "fake-maestro", "--remote-control", "ballet maestro", "/ballet:maestro"])
        self.assertEqual(words[1], "CLAUDE_CODE_PROMPT_CACHE_TTL=1h")

    def test_le_modele_de_maestro_vient_de_maestro_toml(self):
        config = ballet_maestro.read_config()
        config["maestro"] = {"model": "opus"}
        ballet_maestro.write_config(config)
        words = shlex.split(ballet_maestro._maestro_command())
        self.assertEqual(words[words.index("--model") + 1], "opus")

    def test_un_modele_de_maestro_invalide_est_refuse(self):
        ballet_maestro.write_config({"projects": {}, "maestro": {"model": 3}})
        with self.assertRaisesRegex(ballet_maestro.MaestroError, "\\[maestro\\] model in maestro.toml must be a model name"):
            ballet_maestro._maestro_command()

    def test_maestro_ne_charge_aucun_serveur_mcp_et_garde_ses_skills(self):
        with mock.patch.dict("os.environ", {"BALLET_MAESTRO_COMMAND": "claude"}):
            words = shlex.split(ballet_maestro._maestro_command())
        self.assertIn("--strict-mcp-config", words)
        self.assertEqual(json.loads(words[words.index("--mcp-config") + 1]), {"mcpServers": {}})
        self.assertEqual(words[words.index("--tools") + 1].split(","), ["Bash", "Read", "Skill"])

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
        self.assertEqual(self.runtime()["maestro_terminal"], "")

    def test_maestro_un_bail_expire_ne_l_empeche_pas(self):
        ballet_maestro.claim()
        ballet_runtime.update(lease_renewed_at=(datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat(timespec="seconds"))
        self.assertEqual(ballet_maestro.maestro(self.orca), "maestro created: terminal term_1")

    def test_maestro_avec_une_orca_injoignable_ne_cree_rien(self):
        ballet_runtime.update(maestro_terminal="term_1")
        self.orca.unreachable = True
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.maestro(self.orca)
        self.assertEqual(self.orca.ran("terminal", "create"), [])

    def test_maestro_dont_la_creation_echoue_ne_note_aucun_terminal(self):
        self.orca.unreachable = True
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.maestro(self.orca)
        self.assertEqual(self.runtime()["maestro_terminal"], "")

    def test_maestro_ne_touche_ni_a_la_boite_ni_au_monitor_ni_au_bail(self):
        ballet_maestro.mailbox(self.orca)
        ballet_maestro.monitor(self.orca)
        before = self.runtime()
        ballet_maestro.maestro(self.orca)
        after = self.runtime()
        self.assertEqual({**after, "maestro_terminal": ""}, {**before, "maestro_terminal": ""})
        self.assertEqual(after["maestro_terminal"], "term_3")

    def test_maestro_garde_les_reglages_de_sa_table(self):
        ballet_maestro.mailbox(self.orca)
        config = ballet_maestro.read_config()
        config["maestro"] = {"restart_at_context_percent": 20, "context_window_tokens": 500000}
        ballet_maestro.write_config(config)
        ballet_maestro.maestro(self.orca)
        self.assertEqual(self.config()["maestro"], {"restart_at_context_percent": 20, "context_window_tokens": 500000})
        self.assertEqual(self.runtime()["maestro_terminal"], "term_2")

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

    # --- la capacité de Claude (OPP-88) : standby au-dessus de 5 h, le Director au-dessus de 7 jours ---

    RESET = "2026-11-24T15:00:00+00:00"

    def above(self, window, used=93.0, threshold=90):
        """Le Monitor a signalé cette fenêtre au-dessus de son seuil."""
        reading = {"used_percent": used, "resets_at": self.RESET}
        ballet_monitor._save_capacity_alert(window, threshold, reading, None)

    def back_under(self, window):
        ballet_monitor._clear_capacity_alert(window, None)

    def test_au_dessus_du_seuil_de_5_h_aucun_nouveau_lancement_ne_part_et_les_faits_sont_dans_la_decision(self):
        self.trust("antimurphy", "Task")
        self.above("five_hour")
        self.assertEqual(ballet_maestro.decision("antimurphy", "Task"),
                         f"standby (the five_hour window is 93% used, threshold 90%, resets at {self.RESET})")

    def test_redescendu_sous_le_seuil_le_lancement_reprend(self):
        self.trust("antimurphy", "Task")
        self.above("five_hour")
        self.back_under("five_hour")
        self.assertEqual(ballet_maestro.decision("antimurphy", "Task"), "launch")

    def test_au_dessus_du_seuil_hebdomadaire_maestro_demande_au_director(self):
        self.trust("antimurphy", "Task")
        self.above("seven_day", used=91, threshold=85)
        self.assertEqual(ballet_maestro.decision("antimurphy", "Task"),
                         f"ask the Director (the seven_day window is 91% used, threshold 85%, resets at {self.RESET})")

    def test_les_deux_fenetres_au_dessus_la_fenetre_de_5_h_attend_d_abord(self):
        self.trust("antimurphy", "Task")
        self.above("five_hour")
        self.above("seven_day")
        self.assertTrue(ballet_maestro.decision("antimurphy", "Task").startswith("standby (the five_hour window"))
        self.back_under("five_hour")
        self.assertTrue(ballet_maestro.decision("antimurphy", "Task").startswith("ask the Director (the seven_day window"))

    def test_la_capacite_ne_change_que_ce_qui_aurait_ete_lance(self):
        self.trust("antimurphy", "Task")
        self.above("five_hour")
        self.assertIn("ask the Director (Feature is not in auto_launch", ballet_maestro.decision("antimurphy", "Feature"))
        ballet_maestro.pause()
        self.assertEqual(ballet_maestro.decision("antimurphy", "Task"), "ask the Director (auto launch is paused)")

    def test_un_element_bloque_reste_wait_meme_au_dessus_du_seuil(self):
        self.trust("antimurphy", "Task")
        self.above("five_hour")
        self.seen_ready("antimurphy", (7, "Task", "", "Bloqué"))
        ballet_monitor._save_ready("antimurphy", [{**ballet_monitor.read_ready()["antimurphy"][0],
                                                   "blocked_by": [{"item": "#3", "number": 3, "repo": "a/b", "url": "https://x/3"}]}], None)
        self.assertIn("DECISION: wait (blocked by #3, open)", ballet_maestro.ready())

    def test_ready_montre_le_standby_de_chaque_element_a_lancer(self):
        self.trust("antimurphy", "Task")
        self.above("five_hour")
        self.seen_ready("antimurphy", (7, "Task", "Urgent", "Le premier"))
        self.assertEqual(ballet_maestro.ready(),
                         f"antimurphy#7  Task  Urgent  Le premier  https://x/7  DECISION: standby (the five_hour window is 93% used, "
                         f"threshold 90%, resets at {self.RESET})")

    CAPACITY = "capacity · {window} · {way} threshold"

    def capacity_message(self, window="five_hour", way="above"):
        return {"type": "status", "subject": self.CAPACITY.format(window=window, way=way), "from": "term_monitor",
                "body": f"{window} window is 93% used · threshold 90% · resets at {self.RESET}"}

    def test_wait_ecrit_standby_sous_le_depassement_de_5_h(self):
        owner = self.claimed()
        self.above("five_hour")
        self.orca.batches = [[self.capacity_message()]]
        output = ballet_maestro.wait(owner, self.orca)
        self.assertIn(f"resets at {self.RESET}\nDECISION: standby (the five_hour window is 93% used, threshold 90%, resets at {self.RESET})", output)

    def test_wait_demande_au_director_sous_le_depassement_hebdomadaire(self):
        owner = self.claimed()
        self.above("seven_day")
        self.orca.batches = [[self.capacity_message("seven_day")]]
        self.assertIn("DECISION: ask the Director (the seven_day window is 93% used", ballet_maestro.wait(owner, self.orca))

    def test_wait_dit_de_relire_ready_sous_la_redescente(self):
        owner = self.claimed()
        self.orca.batches = [[self.capacity_message(way="below")]]
        self.assertIn("DECISION: resume (run ready and apply each verdict)", ballet_maestro.wait(owner, self.orca))

    def test_un_depassement_deja_leve_ou_une_redescente_deja_reperdue_attendent(self):
        owner = self.claimed()
        self.orca.batches = [[self.capacity_message()]]
        self.assertIn("DECISION: wait (five_hour window is back under its threshold now)", ballet_maestro.wait(owner, self.orca))
        self.above("five_hour")
        self.orca.batches = [[self.capacity_message(way="below")]]
        self.assertIn("DECISION: wait (five_hour window is above its threshold again)", ballet_maestro.wait(owner, self.orca))

    def test_recap_ecrit_aussi_la_decision_de_capacite_et_ne_note_pas_le_monitor_comme_un_conductor(self):
        owner = self.claimed()
        self.above("five_hour")
        event = self.capacity_message()
        self.orca.history = [self.row(1, subject=event["subject"], body=event["body"])]
        self.assertIn("DECISION: standby (the five_hour window", ballet_maestro.recap(owner, self.orca))
        self.assertEqual(ballet_conductors.read(), {})

    def test_une_config_de_capacite_invalide_ne_bloque_pas_les_decisions(self):
        """Le Monitor la signale à chaque tour ; la règle, elle, ne lit que l'état qu'il a noté."""
        self.trust("antimurphy", "Task")
        config = ballet_maestro.read_config()
        config["capacity"] = {"five_hour_threshold": 150}
        ballet_maestro.write_config(config)
        self.assertEqual(ballet_maestro.decision("antimurphy", "Task"), "launch")

    # --- pause, resume ---

    def test_pause_se_note_dans_l_etat_et_resume_la_retire(self):
        self.assertIn("paused", ballet_maestro.pause())
        self.assertTrue(self.runtime()["paused_at"])
        self.assertIn("resumed", ballet_maestro.resume())
        self.assertEqual(self.runtime()["paused_at"], "")

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
        ballet_monitor._save_ready(alias, [
            {"item": f"#{number}", "number": number, "type": kind, "priority": priority, "title": title, "url": f"https://x/{number}"}
            for number, kind, priority, title in items], None)

    def test_ready_liste_les_elements_prets_dans_l_ordre_de_la_file_avec_leur_decision(self):
        self.trust("antimurphy", "Task")
        self.seen_ready("antimurphy", (7, "Task", "Urgent", "Le premier"), (3, "Feature", "", "Le second"))
        lines = ballet_maestro.ready().splitlines()
        self.assertEqual(lines[0], "antimurphy#7  Task  Urgent  Le premier  https://x/7  DECISION: launch")
        self.assertEqual(lines[1], "antimurphy#3  Feature  -  Le second  https://x/3  DECISION: ask the Director (Feature is not in auto_launch of antimurphy)")

    def seen_with_dependencies(self, alias, number, blocked_by=(), doubt=""):
        """Ce que le Monitor a vu des dépendances d'un élément déjà noté prêt."""
        items = ballet_monitor.read_ready()[alias]
        for item in items:
            if item["number"] == number:
                item["blocked_by"] = [{"item": f"#{found}", "number": found, "repo": "acme/shop", "url": f"https://x/{found}"} for found in blocked_by]
                item["doubt"] = doubt
        ballet_monitor._save_ready(alias, items, None)

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
        items = ballet_monitor.read_ready()["antimurphy"]
        items[0]["blocked_by"] = [{"item": "acme/api#5", "number": 5, "repo": "acme/api", "url": "https://x/5"}]
        ballet_monitor._save_ready("antimurphy", items, None)
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
                "body": f"The rehearsal Conductor of {key} finished at x and its terminal {terminal} is still open after 10 min."}

    def test_un_conductor_fini_signale_se_ferme_quand_rien_n_a_change(self):
        owner = self.claimed()
        ballet_conductors.record_launch("antimurphy#12", "antimurphy", "12", "rehearsal", "term_9")
        ballet_conductors.note_events([{"type": "status", "from": "term_9", "subject": "antimurphy#12 · done"}])
        self.orca.batches = [[self.finished_message()]]
        self.assertIn("still open after 10 min.\nDECISION: close", ballet_maestro.wait(owner, self.orca))

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

    # --- un Conductor qui n'écrit plus ---

    def idle_message(self, notice=1, key="antimurphy#12"):
        return {"type": "status", "subject": f"{key} · idle", "from": "term_monitor",
                "body": f"Rehearsal FEAT-001.1 · idle notice {notice} of 2 · no event for 25 min since x · waiting on the dancer (turn started y)"}

    def running_conductor(self, kind="rehearsal", terminal="term_9"):
        ballet_conductors.record_launch("antimurphy#12", "antimurphy", "12", kind, terminal)

    def test_l_avis_1_d_un_conductor_idle_se_relance(self):
        owner = self.claimed()
        self.running_conductor()
        self.orca.batches = [[self.idle_message(1)]]
        self.assertTrue(ballet_maestro.wait(owner, self.orca).endswith("waiting on the dancer (turn started y)\nDECISION: nudge"))

    def test_l_avis_2_demande_au_director_et_lui_propose_d_arreter_le_conductor(self):
        self.running_conductor()
        self.assertEqual(ballet_maestro.idle_decision("antimurphy#12", self.idle_message(2)["body"]),
                         "ask the Director (still idle after a reminder: offer to stop it)")

    def test_un_conductor_qui_ne_tourne_plus_n_est_pas_relance(self):
        self.running_conductor()
        ballet_conductors.note_events([{"type": "status", "from": "term_9", "subject": "antimurphy#12 · done"}])
        self.assertEqual(ballet_maestro.idle_decision("antimurphy#12", self.idle_message(1)["body"]),
                         "wait (antimurphy#12 is finished now)")
        self.assertEqual(ballet_maestro.idle_decision("antimurphy#99", self.idle_message(1)["body"]),
                         "wait (antimurphy#99 is not in the registry anymore)")

    def test_la_decision_idle_s_ecrit_aussi_dans_le_recap(self):
        owner = self.claimed()
        self.running_conductor()
        self.orca.history = [{**self.idle_message(2), "id": "m1", "run_id": self.runtime()["mailbox_run"], "sequence": 1}]
        self.assertIn("DECISION: ask the Director (still idle after a reminder", ballet_maestro.recap(owner, self.orca))

    def test_nudge_tape_le_texte_fixe_dans_le_terminal_d_une_rehearsal(self):
        self.running_conductor("rehearsal")
        self.orca.terminals.append("term_9")
        self.assertEqual(ballet_maestro.nudge("antimurphy#12", self.orca), "nudged antimurphy#12 (terminal term_9)")
        send = self.orca.ran("terminal", "send")[0]
        script = Path(ballet_maestro.__file__).resolve().with_name("ballet_rehearsal.py")
        self.assertEqual(send[send.index("--terminal") + 1], "term_9")
        self.assertEqual(send[send.index("--text") + 1],
                         f"Ballet: your Rehearsal has been idle for a while. Run `python3 {script} nudge` now, then follow its NEXT.")
        self.assertIn("--enter", send)

    def test_nudge_d_un_workshop_vise_le_script_du_workshop(self):
        self.running_conductor("workshop")
        self.orca.terminals.append("term_9")
        ballet_maestro.nudge("antimurphy#12", self.orca)
        text = (lambda send: send[send.index("--text") + 1])(self.orca.ran("terminal", "send")[0])
        self.assertIn("your Workshop has been idle", text)
        self.assertIn("ballet_workshop.py nudge", text)

    def test_nudge_refuse_un_conductor_inconnu_sans_genre_ou_au_terminal_mort(self):
        with self.assertRaises(ballet_maestro.MaestroError):
            ballet_maestro.nudge("antimurphy#12", self.orca)
        self.known_conductor()
        with self.assertRaisesRegex(ballet_maestro.MaestroError, "not a Conductor Maestro launched"):
            ballet_maestro.nudge("antimurphy#12", self.orca)
        self.running_conductor()
        with self.assertRaisesRegex(ballet_maestro.MaestroError, "is gone"):
            ballet_maestro.nudge("antimurphy#12", self.orca)
        self.assertEqual(self.orca.ran("terminal", "send"), [])

    def test_la_ligne_de_commande_nudge(self):
        self.running_conductor()
        self.orca.terminals.append("term_9")
        self.assertEqual(self.run_main("nudge", "antimurphy#12")[0], 0)
        self.assertEqual(len(self.orca.ran("terminal", "send")), 1)
        self.assertEqual(self.run_main("nudge")[0], 2)

    def test_le_delai_d_inactivite_est_un_entier_positif_ou_nul_et_20_par_defaut(self):
        self.assertEqual(ballet_maestro.idle_minutes({}), 20)
        self.assertEqual(ballet_maestro.idle_minutes({"conductors": {"idle_after_minutes": 0}}), 0)
        for wrong in (-1, "20", True, 2.5):
            with self.subTest(value=wrong), self.assertRaises(ballet_maestro.MaestroError) as refused:
                ballet_maestro.idle_minutes({"conductors": {"idle_after_minutes": wrong}})
            self.assertIn("idle_after_minutes", str(refused.exception))

    # --- le contexte de Maestro ---

    def test_le_seuil_de_redemarrage_est_un_pourcentage_de_0_a_100_et_30_par_defaut(self):
        self.assertEqual(ballet_maestro.restart_percent({}), 30)
        self.assertEqual(ballet_maestro.restart_percent({"maestro": {"restart_at_context_percent": 0}}), 0)
        self.assertEqual(ballet_maestro.restart_percent({"maestro": {"restart_at_context_percent": 100}}), 100)
        for wrong in (-1, 101, "30", True, 2.5):
            with self.subTest(value=wrong), self.assertRaises(ballet_maestro.MaestroError) as refused:
                ballet_maestro.restart_percent({"maestro": {"restart_at_context_percent": wrong}})
            self.assertIn("restart_at_context_percent", str(refused.exception))

    def test_la_fenetre_de_contexte_est_un_entier_positif_et_un_million_par_defaut(self):
        self.assertEqual(ballet_maestro.context_window({}), 1_000_000)
        self.assertEqual(ballet_maestro.context_window({"maestro": {"context_window_tokens": 200000}}), 200000)
        for wrong in (0, -5, "1000000", True, 1e6):
            with self.subTest(value=wrong), self.assertRaises(ballet_maestro.MaestroError) as refused:
                ballet_maestro.context_window({"maestro": {"context_window_tokens": wrong}})
            self.assertIn("context_window_tokens", str(refused.exception))

    def context_message(self, session="s-1", subject="maestro · context over threshold"):
        return {"type": "status", "subject": subject, "from": "term_monitor",
                "body": f"Maestro's context is 312000 tokens · 31% of 1000000 · threshold 30% · session {session}"}

    def claimed_in_session(self, session="s-1"):
        ballet_maestro.mailbox(self.orca)
        with mock.patch.dict("os.environ", {"CLAUDE_CODE_SESSION_ID": session}):
            return ballet_maestro.claim().rsplit(" ", 1)[1]

    def test_un_contexte_au_dessus_du_seuil_donne_la_decision_restart(self):
        owner = self.claimed_in_session("s-1")
        self.orca.batches = [[self.context_message("s-1")]]
        self.assertIn("session s-1\nDECISION: restart", ballet_maestro.wait(owner, self.orca))

    def test_la_decision_restart_se_lit_aussi_dans_recap(self):
        owner = self.claimed_in_session("s-1")
        event = self.context_message("s-1")
        self.orca.history = [self.row(1, subject=event["subject"], body=event["body"])]
        self.assertIn("session s-1\nDECISION: restart", ballet_maestro.recap(owner, self.orca))

    def test_recap_d_un_nouveau_maestro_ne_redemande_pas_le_redemarrage_qui_a_eu_lieu(self):
        owner = self.claimed_in_session("s-2")
        event = self.context_message("s-1")
        self.orca.history = [self.row(1, subject=event["subject"], body=event["body"])]
        self.assertIn("\nDECISION: wait (it was about session s-1, Maestro is session s-2 now)", ballet_maestro.recap(owner, self.orca))

    def test_un_redemarrage_deja_demande_ne_se_redemande_pas(self):
        owner = self.claimed_in_session("s-1")
        ballet_runtime.update(restart_terminal="term_7", restart_owns_pause=True)
        self.orca.batches = [[self.context_message("s-1")]]
        self.assertIn("\nDECISION: wait (restart already scheduled)", ballet_maestro.wait(owner, self.orca))

    def test_un_evenement_d_une_session_qui_n_est_plus_maestro_ne_fait_pas_redemarrer(self):
        owner = self.claimed_in_session("s-2")
        self.orca.batches = [[self.context_message("s-1")]]
        self.assertIn("\nDECISION: wait (it was about session s-1, Maestro is session s-2 now)", ballet_maestro.wait(owner, self.orca))

    def test_un_evenement_sans_session_connue_dans_le_bail_donne_restart(self):
        ballet_maestro.mailbox(self.orca)
        with mock.patch.dict("os.environ", clear=False) as environment:
            environment.pop("CLAUDE_CODE_SESSION_ID", None)
            owner = ballet_maestro.claim().rsplit(" ", 1)[1]
        self.orca.batches = [[self.context_message("s-1")]]
        self.assertIn("\nDECISION: restart", ballet_maestro.wait(owner, self.orca))

    def test_les_autres_messages_de_maestro_n_ont_pas_de_decision(self):
        owner = self.claimed_in_session("s-1")
        self.orca.batches = [[self.context_message("s-1", subject="maestro · restart abandoned")]]
        self.assertNotIn("DECISION", ballet_maestro.wait(owner, self.orca))

    def test_un_evenement_de_contexte_ne_touche_pas_au_registre_des_conductors(self):
        owner = self.claimed_in_session("s-1")
        self.orca.batches = [[self.context_message("s-1")]]
        ballet_maestro.wait(owner, self.orca)
        self.assertEqual(ballet_conductors.read(), {})

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
        self.assertTrue(self.runtime()["paused_at"])
        self.assertEqual(self.run_main("resume")[0], 0)
        self.assertEqual(self.runtime()["paused_at"], "")
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

    def test_la_ligne_de_commande_tell_override_joint_les_mots_de_la_raison(self):
        self.known_conductor()
        self.orca.terminals.append("term_9")
        self.assertEqual(self.run_main("tell", "--override", "antimurphy#12", "limit", "lifted")[0], 0)
        send = self.orca.ran("terminal", "send")[0]
        self.assertEqual(send[send.index("--text") + 1], "Director overrides: limit lifted")

    def test_un_wait_sans_jeton_est_un_usage_invalide(self):
        self.assertEqual(self.run_main("wait")[0], 2)

    def test_un_refus_sort_avec_un_et_le_dit(self):
        self.orca.unreachable = True
        code, _, err = self.run_main("mailbox")
        self.assertEqual(code, 1)
        self.assertIn("could not connect to Orca", err)


if __name__ == "__main__":
    unittest.main()
