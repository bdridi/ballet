import io
import json
import shlex
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_conductors  # noqa: E402
import ballet_launch  # noqa: E402
import ballet_maestro  # noqa: E402
import ballet_program  # noqa: E402
from ballet_launch import LaunchError  # noqa: E402
from ballet_rehearsal import Rehearsal, Session  # noqa: E402

PROFILE = """[project]
specs = "specs/"

[repos.antimurphy]
path = "."
proof = "pnpm proof"
"""

BACKLOG = """# Backlog

## Next up

1. **CAP-001** a capability, cut first
2. **BUG-004** · Stock goes negative
3. **FEAT-009** · Something else

## Later

- OPP-77 · far away
"""

URL = "https://claude.ai/code/session_01ABC"


class FakeOrca:
    """La CLI Orca, avec juste ce que le lancement lit ; chaque commande est notée."""

    def __init__(self):
        self.commands = []
        self.terminals = []              # les terminaux vivants
        self.created = 0
        self.screen = ""                 # ce que `terminal read` montre
        self.unreadable = False          # `terminal read` échoue
        self.unreachable = False
        self.unknown_folder = False      # le dossier n'est pas un espace de travail Orca

    def __call__(self, arguments):
        self.commands.append(arguments)
        if self.unreachable:
            raise ballet_maestro.MaestroError("This terminal could not connect to Orca.")
        if arguments[:2] == ["terminal", "list"]:
            return json.dumps({"ok": True, "result": {"terminals": [{"handle": handle} for handle in self.terminals]}})
        if arguments[:2] == ["terminal", "create"] and self.unknown_folder:
            raise ballet_maestro.MaestroError('{"ok": false, "error": {"code": "selector_not_found"}}')
        if arguments[:2] == ["terminal", "create"]:
            self.created += 1
            self.terminals.append(f"term_{self.created}")
            return json.dumps({"ok": True, "result": {"terminal": {"handle": f"term_{self.created}"}}})
        if arguments[:2] == ["terminal", "read"]:
            if self.unreadable:
                raise ballet_maestro.MaestroError("terminal_not_found")
            return json.dumps({"ok": True, "result": {"terminal": {"handle": arguments[3], "tail": self.screen.splitlines()}}})
        return "{}"

    def ran(self, *prefix):
        return [command for command in self.commands if command[:len(prefix)] == list(prefix)]


class BalletLaunchTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.state = self.root / "ballet-home"
        environment = mock.patch.dict("os.environ", {"BALLET_HOME": str(self.state)})
        environment.start()
        self.addCleanup(environment.stop)
        self.orca = FakeOrca()
        self.home = self.project("antimurphy")
        self.dependencies = {}                  # numéro d'issue → ce que GitHub dit de ses dépendances (rien par défaut)
        self.unreadable_github = False
        reader = mock.patch("ballet_program.dependencies_of", side_effect=self.read_dependencies)
        self.reader = reader.start()
        self.addCleanup(reader.stop)

    def read_dependencies(self, number, home):
        if self.unreadable_github:
            raise ballet_program.ProgramError("gh did not answer")
        return self.dependencies.get(str(number), {"blocked_by": [], "doubt": ""})

    def blocked_by(self, number, *blockers):
        self.dependencies[str(number)] = {"blocked_by": [{"item": f"#{found}", "number": found, "repo": "acme/shop",
                                                            "url": f"https://github.com/acme/shop/issues/{found}"} for found in blockers],
                                          "doubt": ""}

    def project(self, name):
        folder = self.root / name
        folder.mkdir()
        ballet_maestro.add_project(name, str(folder))
        return folder

    def rehearsal(self, item="#12", project="antimurphy"):
        return ballet_launch.launch_rehearsal(project, item, self.orca, url_wait=0)

    def workshop(self, item="", project="antimurphy"):
        return ballet_launch.launch_workshop(project, item, self.orca, url_wait=0)

    def limits(self, **limits):
        config = ballet_maestro.read_config()
        config["limits"] = limits
        ballet_maestro.write_config(config)

    def conductors(self):
        return ballet_conductors.read()

    def forget_launches(self):
        (self.state / "conductors.json").unlink(missing_ok=True)
        self.orca.terminals.clear()
        self.orca.commands.clear()

    def create_command(self):
        return self.orca.ran("terminal", "create")[0]

    def option(self, command, name):
        return command[command.index(name) + 1]

    def assertRefused(self, launch, pattern):
        created = len(self.orca.ran("terminal", "create"))
        with self.assertRaisesRegex(LaunchError, pattern):
            launch()
        self.assertEqual(len(self.orca.ran("terminal", "create")), created, "un refus ne crée aucun terminal")

    # --- la commande construite ---

    def test_la_rehearsal_ouvre_un_terminal_dans_le_projet_titre_par_son_element(self):
        self.rehearsal("#12")
        create = self.create_command()
        self.assertEqual(self.option(create, "--worktree"), f"path:{self.home}")
        self.assertEqual(self.option(create, "--title"), "antimurphy#12")
        self.assertIn("--json", create)

    def test_la_commande_met_le_prompt_avant_les_options_et_n_autorise_que_python(self):
        self.rehearsal("#12")
        words = shlex.split(self.option(self.create_command(), "--command"))
        self.assertEqual(words, ["claude", "--remote-control", "antimurphy#12", "/ballet:rehearsal #12",
                                 "--allowedTools", "Bash(python3:*)", "Edit(.ballet/run/**)"])
        self.assertLess(words.index("/ballet:rehearsal #12"), words.index("--allowedTools"))

    def test_la_commande_se_tape_telle_quelle_dans_un_shell(self):
        self.rehearsal("#12")
        command = self.option(self.create_command(), "--command")
        self.assertIn("'antimurphy#12'", command)
        self.assertIn("'/ballet:rehearsal #12'", command)
        self.assertIn("'Bash(python3:*)'", command)

    def test_un_numero_se_lance_comme_une_issue_avec_ou_sans_diese(self):
        for text in ("12", "#12"):
            self.forget_launches()
            self.rehearsal(text)
            words = shlex.split(self.option(self.create_command(), "--command"))
            self.assertEqual(words[3], "/ballet:rehearsal #12")
            self.assertEqual(self.option(self.create_command(), "--title"), "antimurphy#12")

    def test_une_feature_sans_issue_se_lance_par_son_identifiant(self):
        self.rehearsal("FEAT-002")
        words = shlex.split(self.option(self.create_command(), "--command"))
        self.assertEqual(words[2:4], ["antimurphy#FEAT-002", "/ballet:rehearsal FEAT-002"])

    def test_le_workshop_se_lance_en_autopilot_sur_son_element(self):
        self.workshop("BUG-004")
        words = shlex.split(self.option(self.create_command(), "--command"))
        self.assertEqual(words[2:4], ["antimurphy#BUG-004", "/ballet:workshop --autopilot BUG-004"])

    def test_le_workshop_sans_element_prend_la_premiere_ligne_de_next_up(self):
        (self.home / ".ballet").mkdir()
        (self.home / ".ballet" / "config.toml").write_text(PROFILE, encoding="utf-8")
        (self.home / "specs").mkdir()
        (self.home / "specs" / "backlog.md").write_text(BACKLOG, encoding="utf-8")
        output = self.workshop()
        self.assertIn("antimurphy#BUG-004", output)
        words = shlex.split(self.option(self.create_command(), "--command"))
        self.assertEqual(words[3], "/ballet:workshop --autopilot BUG-004")

    def test_le_workshop_sans_element_refuse_un_projet_sans_backlog(self):
        (self.home / ".ballet").mkdir()
        (self.home / ".ballet" / "config.toml").write_text(PROFILE, encoding="utf-8")
        self.assertRefused(self.workshop, "no backlog")

    def test_la_variable_d_environnement_remplace_l_agent_et_garde_les_arguments(self):
        with mock.patch.dict("os.environ", {"BALLET_CONDUCTOR_COMMAND": "sh -c 'echo hi; exec cat'"}):
            self.rehearsal("#12")
        words = shlex.split(self.option(self.create_command(), "--command"))
        self.assertEqual(words, ["sh", "-c", "echo hi; exec cat", "--remote-control", "antimurphy#12",
                                 "/ballet:rehearsal #12", "--allowedTools", "Bash(python3:*)", "Edit(.ballet/run/**)"])

    # --- les garde-fous ---

    def test_un_projet_inconnu_est_refuse_et_les_connus_sont_listes(self):
        self.assertRefused(lambda: self.rehearsal("#12", project="nowhere"), "unknown project nowhere \\(known: antimurphy\\)")

    def test_un_element_mal_ecrit_est_refuse(self):
        self.assertRefused(lambda: self.rehearsal("douze"), "not an item: douze")
        self.assertRefused(lambda: self.workshop("douze"), "not a backlog item: douze")

    def test_un_element_deja_vivant_dans_le_registre_est_refuse(self):
        self.rehearsal("#12")
        self.orca.commands.clear()
        with self.assertRaisesRegex(LaunchError, "antimurphy#12 already has a Conductor running, in terminal term_1"):
            self.rehearsal("12")
        self.assertEqual(self.orca.ran("terminal", "create"), [])

    def test_un_conductor_dont_le_terminal_est_ferme_ne_bloque_plus(self):
        self.rehearsal("#12")
        self.orca.terminals.clear()
        self.rehearsal("#12")
        self.assertEqual(self.conductors()["antimurphy#12"]["terminal"], "term_2")

    def test_un_conductor_fini_ne_bloque_plus_son_element(self):
        self.rehearsal("#12")
        ballet_conductors.note_events([{"type": "status", "from": "term_1", "subject": "antimurphy#12 · done"}])
        self.rehearsal("#12")
        self.assertEqual(self.conductors()["antimurphy#12"]["terminal"], "term_2")

    def test_une_session_de_rehearsal_ouverte_dans_le_projet_est_refusee(self):
        import ballet_rehearsal
        ballet_rehearsal._save_session(Session(item="#12", current="FEAT-004.1"), self.home)
        ballet_rehearsal._save(Rehearsal(id="FEAT-004.1", issue="#12", repo="repo", status="escalated"), self.home)
        self.assertRefused(self.rehearsal, "antimurphy#12 has an open session .*state escalated, Rehearsal FEAT-004.1")

    def test_une_session_finie_ne_bloque_pas(self):
        import ballet_rehearsal
        ballet_rehearsal._save_session(Session(item="#12", status="done"), self.home)
        self.rehearsal("#12")
        self.assertEqual(len(self.orca.ran("terminal", "create")), 1)

    def test_un_workshop_ouvert_dans_le_projet_est_refuse(self):
        run = self.home / ".ballet" / "run"
        run.mkdir(parents=True)
        (run / "workshop-BUG-004.json").write_text(json.dumps({"item": "BUG-004", "repo": "r", "status": "escalated"}), encoding="utf-8")
        self.assertRefused(lambda: self.workshop("BUG-004"), "antimurphy#BUG-004 has an open session .*state escalated")

    def test_le_plafond_de_conductors_simultanes_est_de_trois_par_defaut(self):
        for number in (1, 2, 3):
            self.rehearsal(f"#{number}")
        self.assertRefused(lambda: self.rehearsal("#4"), "3 Conductor\\(s\\) already running .*limit is 3 .*max_running")

    def test_le_plafond_vient_de_la_table_limits_de_maestro_toml(self):
        self.limits(max_running=1)
        self.rehearsal("#1")
        self.assertRefused(lambda: self.rehearsal("#2"), "limit is 1")

    def test_le_plafond_compte_les_conductors_de_tous_les_projets_et_ignore_les_morts_et_les_finis(self):
        other = self.project("beta")
        self.limits(max_running=2)
        self.rehearsal("#1")
        ballet_launch.launch_rehearsal("beta", "#2", self.orca, url_wait=0)
        self.orca.terminals.remove("term_1")        # le premier est mort : il ne compte plus
        self.rehearsal("#3")
        self.assertRefused(lambda: self.rehearsal("#4"), "2 Conductor\\(s\\) already running")
        ballet_conductors.note_events([{"type": "status", "from": "term_2", "subject": "beta#2 · done"}])   # fini : il ne compte plus
        self.rehearsal("#4")
        self.assertEqual(other.name, "beta")

    def test_le_plafond_du_jour_est_de_dix_par_defaut(self):
        self.limits(max_running=99)
        for number in range(10):
            self.rehearsal(f"#{number + 1}")
        self.assertRefused(lambda: self.rehearsal("#11"), "10 launch\\(es\\) today already: the limit is 10 .*max_per_day")

    def test_le_plafond_du_jour_compte_aussi_un_element_relance(self):
        self.limits(max_running=99, max_per_day=2)
        self.rehearsal("#1")
        self.orca.terminals.clear()
        self.rehearsal("#1")
        self.assertRefused(lambda: self.rehearsal("#2"), "2 launch\\(es\\) today")

    def test_les_lancements_d_hier_ne_comptent_pas_dans_le_jour(self):
        self.limits(max_running=99, max_per_day=1)
        yesterday = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(timespec="seconds")
        self.state.mkdir(exist_ok=True)
        (self.state / "conductors.json").write_text(json.dumps({"antimurphy#1": {"terminal": "term_gone", "starts": [yesterday]}}), encoding="utf-8")
        self.rehearsal("#2")
        self.assertRefused(lambda: self.rehearsal("#3"), "1 launch\\(es\\) today")

    def test_un_plafond_mal_ecrit_est_refuse(self):
        self.limits(max_running="beaucoup")
        self.assertRefused(self.rehearsal, "max_running .* must be a whole number")

    def test_une_orca_injoignable_ne_lance_rien(self):
        self.orca.unreachable = True
        with self.assertRaises(ballet_maestro.MaestroError):
            self.rehearsal()
        self.assertFalse((self.state / "conductors.json").exists())

    def test_un_dossier_inconnu_d_orca_est_refuse_en_disant_comment_l_ajouter(self):
        self.orca.unknown_folder = True
        with self.assertRaisesRegex(LaunchError, "orca repo add --path"):
            self.rehearsal()
        self.assertFalse((self.state / "conductors.json").exists())

    # --- le registre ---

    def test_le_lancement_ecrit_sa_ligne_et_dit_ce_qui_est_parti(self):
        output = self.rehearsal("#12")
        line = self.conductors()["antimurphy#12"]
        self.assertEqual({key: line[key] for key in ("project", "item", "kind", "terminal", "url", "seen", "event", "state")},
                         {"project": "antimurphy", "item": "12", "kind": "rehearsal", "terminal": "term_1", "url": "",
                          "seen": "", "event": "", "state": "running"})
        self.assertEqual(line["starts"], [line["started"]])
        self.assertEqual(output, f"launched the rehearsal Conductor of antimurphy#12 in {self.home}: terminal term_1, "
                                 "Remote Control URL not found yet")

    def test_le_workshop_est_note_comme_tel(self):
        self.workshop("BUG-004")
        self.assertEqual(self.conductors()["antimurphy#BUG-004"]["kind"], "workshop")

    def test_l_url_remote_control_lue_dans_le_terminal_va_dans_la_ligne_et_dans_la_sortie(self):
        self.orca.screen = f"Claude Code\n/remote-control is active\n  {URL}\n"
        output = self.rehearsal("#12")
        self.assertEqual(self.conductors()["antimurphy#12"]["url"], URL)
        self.assertTrue(output.endswith(f"Remote Control {URL}"))
        read = self.orca.ran("terminal", "read")[0]
        self.assertEqual(self.option(read, "--terminal"), "term_1")

    def test_sans_url_la_ligne_reste_et_l_url_est_vide(self):
        self.orca.screen = "no url here"
        self.rehearsal("#12")
        self.assertEqual(self.conductors()["antimurphy#12"]["url"], "")

    def test_la_lecture_du_terminal_attend_l_url_quelques_secondes_sans_bloquer(self):
        ticks = iter([0, 0.5, 100])
        with mock.patch.object(ballet_launch.time, "monotonic", side_effect=lambda: next(ticks)), \
                mock.patch.object(ballet_launch.time, "sleep") as sleep:
            ballet_launch.launch_rehearsal("antimurphy", "#12", self.orca, url_wait=2)
        self.assertEqual(len(self.orca.ran("terminal", "read")), 2)
        self.assertEqual(sleep.call_count, 1)

    def test_un_terminal_illisible_n_empeche_pas_le_lancement(self):
        self.orca.unreadable = True
        self.rehearsal("#12")
        self.assertEqual(self.conductors()["antimurphy#12"]["url"], "")

    def test_un_relancement_garde_les_dates_des_lancements_precedents(self):
        self.limits(max_running=99)
        self.rehearsal("#12")
        self.orca.terminals.clear()
        self.rehearsal("#12")
        self.assertEqual(len(self.conductors()["antimurphy#12"]["starts"]), 2)

    def test_wait_complete_la_ligne_du_lancement_sans_perdre_ses_champs(self):
        self.orca.screen = URL
        self.rehearsal("#12")
        ballet_conductors.note_events([{"type": "status", "from": "term_1", "subject": "antimurphy#12 · escalate"}])
        line = self.conductors()["antimurphy#12"]
        self.assertEqual((line["event"], line["state"], line["kind"], line["url"]), ("escalate", "running", "rehearsal", URL))
        self.assertTrue(line["seen"])

    def test_un_done_marque_la_ligne_finished_et_un_nouvel_evenement_la_rouvre(self):
        self.rehearsal("#12")
        ballet_conductors.note_events([{"type": "status", "from": "term_1", "subject": "antimurphy#12 · done"}])
        self.assertEqual(self.conductors()["antimurphy#12"]["state"], "finished")
        ballet_conductors.note_events([{"type": "status", "from": "term_1", "subject": "antimurphy#12 · escalate"}])
        self.assertEqual(self.conductors()["antimurphy#12"]["state"], "running")

    def test_un_conductor_que_maestro_n_a_pas_lance_a_sa_ligne_au_premier_message(self):
        ballet_conductors.note_events([{"type": "status", "from": "term_7", "subject": "am#BUG-004 · done"}])
        self.assertEqual({key: self.conductors()["am#BUG-004"][key] for key in ("project", "item", "kind", "terminal", "state")},
                         {"project": "am", "item": "BUG-004", "kind": "", "terminal": "term_7", "state": "finished"})

    def test_une_ligne_d_avant_l_etape_3_se_lit_par_son_dernier_evenement(self):
        self.assertEqual(ballet_conductors.state_of({"terminal": "t", "event": "done"}), "finished")
        self.assertEqual(ballet_conductors.state_of({"terminal": "t", "event": "escalate"}), "running")
        self.assertEqual(ballet_conductors.state_of({"terminal": "t"}), "running")

    def test_wait_note_un_done_sur_la_ligne_lancee(self):
        owner = ballet_maestro.claim().split()[-1]
        ballet_maestro.write_config({**ballet_maestro.read_config(), "mailbox": {"terminal": "term_box", "run": "run_1"}})
        self.rehearsal("#12")
        message = {"type": "status", "from": "term_1", "subject": "antimurphy#12 · done", "body": "b"}
        with mock.patch.object(ballet_maestro, "_wait_for_messages", return_value=[message]):
            ballet_maestro.wait(owner, self.orca)
        self.assertEqual(self.conductors()["antimurphy#12"]["state"], "finished")

    # --- status et tell ---

    def test_status_montre_les_conductors_lances_avec_l_etat_de_leur_terminal(self):
        self.orca.screen = URL
        self.rehearsal("#12")
        self.rehearsal("#13")
        self.orca.terminals.remove("term_2")
        lines = ballet_maestro.status(self.orca).splitlines()
        self.assertEqual(lines[0], "no open session in any project")
        self.assertEqual(lines[2], "Conductors:")
        self.assertEqual(lines[3], f"antimurphy#12  rehearsal  running  term_1 (alive)  no event yet  {URL}")
        self.assertEqual(lines[4], "antimurphy#13  rehearsal  running  term_2 (gone)  no event yet  " + URL)

    def test_status_cache_les_conductors_finis_dont_le_terminal_est_ferme(self):
        self.rehearsal("#12")
        ballet_conductors.note_events([{"type": "status", "from": "term_1", "subject": "antimurphy#12 · done"}])
        self.assertIn("antimurphy#12  rehearsal  finished  term_1 (alive)  last: done", ballet_maestro.status(self.orca))
        self.orca.terminals.clear()
        self.assertEqual(ballet_maestro.status(self.orca), "no open session in any project")

    def test_status_dit_que_l_etat_du_terminal_est_inconnu_quand_orca_ne_repond_pas(self):
        self.rehearsal("#12")
        self.orca.unreachable = True
        self.assertIn("term_1 (state unknown)", ballet_maestro.status(self.orca))

    def test_status_sans_registre_ne_parle_pas_a_orca(self):
        ballet_maestro.status(self.orca)
        self.assertEqual(self.orca.commands, [])

    def test_tell_marche_des_le_lancement(self):
        self.rehearsal("#12")
        self.assertEqual(ballet_maestro.tell("antimurphy#12", "go on", self.orca), "told antimurphy#12 (terminal term_1)")
        send = self.orca.ran("terminal", "send")[0]
        self.assertEqual(self.option(send, "--text"), "Director answers: go on")

    # --- les dépendances : un bloqueur ouvert refuse le lancement ---

    def test_un_element_dont_un_bloqueur_est_ouvert_est_refuse_et_le_bloqueur_est_nomme(self):
        self.blocked_by(12, 3)
        with self.assertRaisesRegex(LaunchError, r"antimurphy#12 is blocked by #3 \(https://github.com/acme/shop/issues/3\), still open"):
            self.rehearsal("#12")
        self.assertEqual((self.orca.ran("terminal", "create"), self.conductors()), ([], {}))

    def test_tous_les_bloqueurs_ouverts_sont_nommes(self):
        self.blocked_by(12, 3, 5)
        with self.assertRaisesRegex(LaunchError, r"blocked by #3 .*, #5 "):
            self.rehearsal("12")

    def test_un_bloqueur_d_un_autre_repo_est_nomme_avec_son_repo(self):
        self.dependencies["12"] = {"blocked_by": [{"item": "acme/api#5", "number": 5, "repo": "acme/api", "url": "https://github.com/acme/api/issues/5"}],
                                   "doubt": ""}
        with self.assertRaisesRegex(LaunchError, "blocked by acme/api#5"):
            self.rehearsal("#12")

    def test_le_refus_vaut_meme_quand_le_director_a_demande_ce_lancement(self):
        self.blocked_by(12, 3)
        code, out, err = self.run_main("rehearsal", "antimurphy", "#12")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("launch: antimurphy#12 is blocked by #3", err)
        self.assertIn("--ignore-blockers", err)

    def test_ignore_blockers_passe_outre_et_ne_lit_meme_pas_github(self):
        self.blocked_by(12, 3)
        ballet_launch.launch_rehearsal("antimurphy", "#12", self.orca, url_wait=0, ignore_blockers=True)
        self.assertEqual(len(self.orca.ran("terminal", "create")), 1)
        self.reader.assert_not_called()

    def test_ignore_blockers_en_ligne_de_commande(self):
        self.blocked_by(12, 3)
        with mock.patch.object(ballet_launch, "_find_remote_control_url", return_value=""):
            code, out, err = self.run_main("rehearsal", "antimurphy", "#12", "--ignore-blockers")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("launched the rehearsal Conductor of antimurphy#12", out)

    def test_ignore_blockers_ne_vaut_que_pour_un_rehearsal(self):
        code, _, err = self.run_main("workshop", "antimurphy", "BUG-004", "--ignore-blockers")
        self.assertEqual(code, 2)
        self.assertIn("usage:", err)

    def test_un_element_sans_bloqueur_ouvert_part(self):
        self.rehearsal("#12")
        self.reader.assert_called_once_with("12", self.home)

    def test_un_element_dont_les_bloqueurs_sont_fermes_part(self):
        self.dependencies["12"] = {"blocked_by": [], "doubt": ""}
        self.assertIn("launched the rehearsal Conductor of antimurphy#12", self.rehearsal("#12"))

    def test_un_doute_sans_bloqueur_ouvert_ne_refuse_pas_le_lancement_que_le_director_demande(self):
        self.dependencies["12"] = {"blocked_by": [], "doubt": "blocker #3 was closed as not planned, not delivered"}
        self.assertIn("launched", self.rehearsal("#12"))

    def test_un_cycle_refuse_le_lancement(self):
        self.blocked_by(12, 13)
        self.dependencies["12"]["doubt"] = "dependency cycle: #12 → #13 → #12"
        with self.assertRaisesRegex(LaunchError, "is blocked by #13"):
            self.rehearsal("#12")

    def test_une_feature_sans_issue_n_a_pas_de_lien_a_lire(self):
        self.rehearsal("FEAT-002")
        self.reader.assert_not_called()

    def test_un_workshop_ne_lit_pas_les_dependances(self):
        self.workshop("BUG-004")
        self.reader.assert_not_called()

    def test_github_injoignable_refuse_au_lieu_de_lancer_a_l_aveugle(self):
        self.unreadable_github = True
        with self.assertRaisesRegex(LaunchError, r"cannot read the blockers of antimurphy#12 \(gh did not answer\)"):
            self.rehearsal("#12")
        self.assertEqual(self.orca.ran("terminal", "create"), [])

    def test_github_injoignable_n_empeche_pas_un_lancement_avec_ignore_blockers(self):
        self.unreadable_github = True
        ballet_launch.launch_rehearsal("antimurphy", "#12", self.orca, url_wait=0, ignore_blockers=True)
        self.assertEqual(len(self.orca.ran("terminal", "create")), 1)

    def test_les_autres_garde_fous_passent_avant_la_lecture_de_github(self):
        self.limits(max_running=0)
        with self.assertRaisesRegex(LaunchError, "limit is 0"):
            self.rehearsal("#12")
        self.reader.assert_not_called()

    # --- la ligne de commande ---

    def run_main(self, *arguments):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ballet_launch.main(["ballet_launch.py", *arguments], orca=self.orca)
        return code, out.getvalue(), err.getvalue()

    def test_main_lance_et_affiche_une_ligne(self):
        with mock.patch.object(ballet_launch, "_find_remote_control_url", return_value=""):
            code, out, err = self.run_main("rehearsal", "antimurphy", "#12")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertIn("antimurphy#12", out)

    def test_main_refuse_avec_le_code_1_et_un_message_en_anglais(self):
        code, out, err = self.run_main("rehearsal", "nowhere", "#12")
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("launch: unknown project nowhere"))

    def test_main_un_usage_invalide_sort_avec_2(self):
        for arguments in ((), ("rehearsal", "antimurphy"), ("workshop",), ("stop", "antimurphy#12")):
            code, _, err = self.run_main(*arguments)
            self.assertEqual(code, 2)
            self.assertIn("usage:", err)


if __name__ == "__main__":
    unittest.main()
