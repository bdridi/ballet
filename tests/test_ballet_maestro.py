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

import ballet_maestro  # noqa: E402
from ballet_rehearsal import Step  # noqa: E402


class FakeOrca:
    """La CLI Orca, avec juste ce que Maestro lit ; chaque commande est notée."""

    def __init__(self):
        self.commands = []
        self.terminals = []          # les terminaux vivants
        self.created = 0
        self.unreachable = False     # Orca ne répond pas
        self.run_failures = 0        # `run-create` échoue ces fois-ci
        self.send_failures = 0       # `send` échoue ces fois-ci

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
        config = {"mailbox": {"terminal": "term_1", "run": "run_1"}, "lease": {"pid": 4242, "since": "2026-11-21T08:00:00Z"},
                  "projects": {"antimurphy": {"path": "/p/antimurphy"}, "mon projet": {"path": "/p/\"quoted\" été\n"}},
                  "limits": {"auto_launch": ["Task", "Bug"], "paused": False}}
        ballet_maestro.write_config(config)
        self.assertEqual(self.config(), config)

    def test_le_toml_reserve_le_bail_et_reste_lisible(self):
        ballet_maestro.write_config(ballet_maestro.read_config())
        text = (self.state / "maestro.toml").read_text(encoding="utf-8")
        self.assertIn("[lease]\npid = 0\nsince = \"\"", text)
        self.assertEqual(self.config()["lease"], {"pid": 0, "since": ""})

    def test_sans_fichier_l_etat_est_vide(self):
        self.assertEqual(ballet_maestro.read_config(), {"mailbox": {}, "lease": {"pid": 0, "since": ""}, "projects": {}})

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
        self.assertEqual(self.config()["lease"], {"pid": 0, "since": ""})

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

    def test_un_refus_sort_avec_un_et_le_dit(self):
        self.orca.unreachable = True
        code, _, err = self.run_main("mailbox")
        self.assertEqual(code, 1)
        self.assertIn("could not connect to Orca", err)


if __name__ == "__main__":
    unittest.main()
