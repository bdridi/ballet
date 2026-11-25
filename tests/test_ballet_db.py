import json
import sqlite3
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_conductors  # noqa: E402
import ballet_db  # noqa: E402
import ballet_journal  # noqa: E402
import ballet_legacy  # noqa: E402
import ballet_maestro  # noqa: E402
import ballet_monitor  # noqa: E402
import ballet_rehearsal  # noqa: E402
import ballet_runtime  # noqa: E402
import ballet_store  # noqa: E402


class BalletDbTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.state = self.root / "ballet-home"
        environment = mock.patch.dict("os.environ", {"BALLET_HOME": str(self.state)})
        environment.start()
        self.addCleanup(environment.stop)

    def migrations(self, *scripts):
        """Un dossier de migrations : (nom, SQL)."""
        folder = self.root / "migrations"
        folder.mkdir(exist_ok=True)
        for name, sql in scripts:
            (folder / name).write_text(sql, encoding="utf-8")
        return folder

    def tables(self, connection):
        return sorted(row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'"))

    # --- les migrations ---

    def test_une_base_neuve_monte_a_la_derniere_migration_du_plugin(self):
        with ballet_db.reading() as connection:
            self.assertEqual(ballet_db.version(connection), 5)
            self.assertEqual(self.tables(connection), ["capacity_alerts", "conductors", "events", "nodes", "ready", "rehearsals", "runtime", "sessions", "workshop_cost_problems", "workshop_cost_watermarks", "workshop_costs", "workshops"])
        self.assertTrue((self.state / "ballet.db").is_file())

    def test_rouvrir_ne_refait_rien(self):
        folder = self.migrations(("0001_init.sql", "CREATE TABLE t (x);"))
        ballet_db.connect(migrations=folder).close()
        connection = ballet_db.connect(migrations=folder)   # un CREATE TABLE rejoué lèverait
        self.assertEqual(ballet_db.version(connection), 1)
        connection.close()

    def test_une_nouvelle_migration_s_applique_seule_et_garde_les_donnees(self):
        folder = self.migrations(("0001_init.sql", "CREATE TABLE t (x);"))
        connection = ballet_db.connect(migrations=folder)
        connection.execute("INSERT INTO t VALUES (42)")
        connection.close()
        self.migrations(("0002_more.sql", "ALTER TABLE t ADD COLUMN y DEFAULT 'neuf';"))
        connection = ballet_db.connect(migrations=folder)
        self.assertEqual(ballet_db.version(connection), 2)
        self.assertEqual(tuple(connection.execute("SELECT x, y FROM t").fetchone()), (42, "neuf"))
        connection.close()

    def test_une_base_migree_est_copiee_avant(self):
        folder = self.migrations(("0001_init.sql", "CREATE TABLE t (x);"))
        ballet_db.connect(migrations=folder).close()
        self.migrations(("0002_more.sql", "CREATE TABLE u (x);"))
        ballet_db.connect(migrations=folder).close()
        copy = sqlite3.connect(self.state / "ballet.db.v1.bak")
        self.assertEqual(copy.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertEqual([row[0] for row in copy.execute("SELECT name FROM sqlite_master WHERE type = 'table'")], ["t"])
        copy.close()

    def test_une_base_neuve_n_a_pas_de_copie(self):
        ballet_db.connect().close()
        self.assertEqual(sorted(path.name for path in self.state.glob("*.bak")), [])

    def test_une_migration_qui_echoue_ne_laisse_rien(self):
        folder = self.migrations(("0001_init.sql", "CREATE TABLE t (x);"), ("0002_bad.sql", "CREATE TABLE u (x); NOT SQL;"))
        with self.assertRaises(sqlite3.Error):
            ballet_db.connect(migrations=folder)
        connection = sqlite3.connect(self.state / "ballet.db")
        self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 0)
        self.assertEqual(connection.execute("SELECT count(*) FROM sqlite_master").fetchone()[0], 0)
        connection.close()

    def test_une_base_plus_recente_que_le_plugin_est_refusee(self):
        self.state.mkdir()
        connection = sqlite3.connect(self.state / "ballet.db")
        connection.execute("PRAGMA user_version = 99")
        connection.close()
        with self.assertRaisesRegex(ballet_db.DatabaseError, "version 99, this plugin knows 5"):
            ballet_db.connect()

    def test_un_nom_de_migration_hors_forme_est_refuse(self):
        folder = self.migrations(("init.sql", "CREATE TABLE t (x);"))
        with self.assertRaisesRegex(ballet_db.DatabaseError, "NNNN_<name>.sql"):
            ballet_db.connect(migrations=folder)

    def test_la_base_est_en_wal(self):
        with ballet_db.reading() as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")

    def test_une_ecriture_interrompue_ne_laisse_rien(self):
        with self.assertRaises(KeyboardInterrupt), ballet_db.writing() as connection:
            ballet_runtime.update_in(connection, mailbox_run="run_1")
            raise KeyboardInterrupt
        self.assertEqual(ballet_runtime.read()["mailbox_run"], "")

    # --- le runtime ---

    def test_le_runtime_vide_se_lit_sans_none(self):
        runtime = ballet_runtime.read()
        self.assertEqual((runtime["mailbox_run"], runtime["lease_pid"], runtime["restart_owns_pause"]), ("", 0, False))

    def test_le_runtime_garde_la_version_de_maestro_et_celle_du_monitor(self):
        ballet_runtime.update(maestro_version="0.48.0", monitor_version="0.47.0")
        runtime = ballet_runtime.read()
        self.assertEqual((runtime["maestro_version"], runtime["monitor_version"]), ("0.48.0", "0.47.0"))

    def test_une_base_d_avant_les_versions_les_lit_vides_sans_erreur(self):
        """Le runtime d'une base à la version 3 : ses lignes restent, les versions sont vides."""
        before = self.root / "migrations-before"
        before.mkdir()
        for migration in sorted(ballet_db.MIGRATIONS.glob("000[123]_*.sql")):
            (before / migration.name).write_text(migration.read_text(encoding="utf-8"), encoding="utf-8")
        old = ballet_db.connect(migrations=before)
        old.execute("UPDATE runtime SET mailbox_run = 'run_1' WHERE one = 1")
        old.close()
        runtime = ballet_runtime.read()
        self.assertEqual((runtime["mailbox_run"], runtime["maestro_version"], runtime["monitor_version"]), ("run_1", "", ""))

    def test_le_runtime_refuse_un_champ_inconnu(self):
        with self.assertRaises(ValueError):
            ballet_runtime.update(mailbox="x")

    # --- le journal ---

    def test_un_noeud_commence_puis_finit_avec_ses_deux_evenements(self):
        with ballet_db.writing() as connection:
            node = ballet_journal.start(connection, "proof", "pnpm proof", ballet_journal.SCRIPT, "conductor", project="am")
            self.assertTrue(ballet_journal.is_open(connection, node))
            ballet_journal.mark(connection, node, "output", "conductor", {"lines": 3})
            self.assertTrue(ballet_journal.end(connection, node, ballet_journal.OK, "conductor"))
            self.assertFalse(ballet_journal.end(connection, node, ballet_journal.FAILED, "conductor"))
        with ballet_db.reading() as connection:
            events = [(row["phase"], row["kind"]) for row in connection.execute("SELECT * FROM events ORDER BY id")]
            outcome = connection.execute("SELECT outcome FROM nodes").fetchone()["outcome"]
        self.assertEqual(events, [("start", "proof"), ("mark", "output"), ("end", "proof")])
        self.assertEqual(outcome, "ok")

    def test_le_registre_suit_le_conductor_dans_son_noeud(self):
        ballet_conductors.record_launch("am#12", "am", "12", "rehearsal", "term_1")
        ballet_conductors.note_events([{"type": "status", "from": "term_1", "subject": "am#12 · escalate"}])
        ballet_conductors.note_events([{"type": "status", "from": "term_1", "subject": "am#12 · done"}])
        ballet_conductors.mark_closed("am#12", "term_1")
        with ballet_db.reading() as connection:
            events = [(row["phase"], row["kind"], row["actor"]) for row in connection.execute("SELECT * FROM events ORDER BY id")]
        self.assertEqual(events, [("start", "launch", "maestro"), ("mark", "escalate", "conductor"),
                                  ("end", "done", "conductor"), ("mark", "closed", "maestro")])
        self.assertEqual(ballet_conductors.read()["am#12"]["state"], "closed")

    def test_un_conductor_qui_parle_apres_sa_fin_tourne_dans_un_nouveau_noeud(self):
        ballet_conductors.record_launch("am#12", "am", "12", "rehearsal", "term_1")
        ballet_conductors.note_events([{"type": "status", "from": "term_1", "subject": "am#12 · done"}])
        ballet_conductors.note_events([{"type": "status", "from": "term_1", "subject": "am#12 · escalate"}])
        with ballet_db.reading() as connection:
            nodes = connection.execute("SELECT ended_at FROM nodes ORDER BY started_at, rowid").fetchall()
        self.assertEqual([node["ended_at"] is None for node in nodes], [False, True])
        line = ballet_conductors.read()["am#12"]
        self.assertEqual((line["state"], line["kind"], line["event"]), ("running", "rehearsal", "escalate"))


class BalletLegacyTest(unittest.TestCase):
    """La reprise, une seule fois, de l'état d'avant la base."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state = Path(self._tmp.name) / "ballet-home"
        self.state.mkdir()
        environment = mock.patch.dict("os.environ", {"BALLET_HOME": str(self.state)})
        environment.start()
        self.addCleanup(environment.stop)

    def old_state(self):
        (self.state / "maestro.toml").write_text(
            '[mailbox]\nterminal = "term_box"\nrun = "run_2"\nprevious_run = "run_1"\n\n'
            '[lease]\nowner = "abc"\npid = 0\nrenewed = "2026-11-22T16:50:33+00:00"\nsession = "s-1"\n\n'
            '[monitor]\nterminal = "term_mon"\n\n[maestro]\nterminal = "term_mae"\nrestart_at_context_percent = 20\n\n'
            '[restart]\nterminal = "term_rst"\npaused = true\n\n'
            '[projects.antimurphy]\npath = "/p/antimurphy"\nauto_launch = ["Task"]\n\n[limits]\nmax_running = 1\n', encoding="utf-8")
        (self.state / "auto_launch_paused").write_text("2026-11-22T10:00:00+00:00\n", encoding="utf-8")
        (self.state / "monitor.json").write_text(json.dumps({
            "projects": {"antimurphy": {"ready": [{"item": "#7", "number": 7, "type": "Task"}]}},
            "maestro": {"context_told": "s-0"}}), encoding="utf-8")
        (self.state / "conductors.json").write_text(json.dumps({
            "antimurphy#59": {"project": "antimurphy", "item": "59", "kind": "rehearsal", "terminal": "term_59", "url": "https://u/59",
                              "started": "2026-11-21T21:37:39+00:00", "starts": ["2026-11-21T21:37:39+00:00"],
                              "seen": "2026-11-21T22:08:12+00:00", "event": "done", "state": "finished"},
            "antimurphy#61": {"project": "antimurphy", "item": "61", "kind": "rehearsal", "terminal": "term_61", "url": "",
                              "started": "2026-11-22T09:00:00+00:00", "starts": [], "seen": "2026-11-22T09:30:00+00:00",
                              "event": "escalate", "state": "running"},
            "am#BUG-4": {"terminal": "term_4", "seen": "2026-11-20T08:00:00+00:00", "event": "escalate"}}), encoding="utf-8")

    def test_l_etat_de_maestro_toml_passe_dans_la_base_et_la_config_reste(self):
        self.old_state()
        ballet_legacy.run_import()
        runtime = ballet_runtime.read()
        self.assertEqual({key: runtime[key] for key in ("mailbox_terminal", "mailbox_run", "mailbox_previous_run", "maestro_terminal",
                                                        "monitor_terminal", "restart_terminal", "restart_owns_pause", "lease_owner",
                                                        "lease_session", "paused_at", "context_told_session")},
                         {"mailbox_terminal": "term_box", "mailbox_run": "run_2", "mailbox_previous_run": "run_1",
                          "maestro_terminal": "term_mae", "monitor_terminal": "term_mon", "restart_terminal": "term_rst",
                          "restart_owns_pause": True, "lease_owner": "abc", "lease_session": "s-1",
                          "paused_at": "2026-11-22T10:00:00+00:00", "context_told_session": "s-0"})
        config = tomllib.loads((self.state / "maestro.toml").read_text(encoding="utf-8"))
        self.assertEqual(config, {"maestro": {"restart_at_context_percent": 20},
                                  "projects": {"antimurphy": {"path": "/p/antimurphy", "auto_launch": ["Task"]}},
                                  "limits": {"max_running": 1}})
        self.assertIn("[lease]", (self.state / "maestro.toml.imported").read_text(encoding="utf-8"))

    def test_le_registre_et_la_file_sont_repris_avec_leurs_noeuds(self):
        self.old_state()
        ballet_legacy.run_import()
        registry = ballet_conductors.read()
        self.assertEqual({key: (line["state"], line["kind"], line["event"], line["seen"]) for key, line in registry.items()},
                         {"antimurphy#59": ("finished", "rehearsal", "done", "2026-11-21T22:08:12+00:00"),
                          "antimurphy#61": ("running", "rehearsal", "escalate", "2026-11-22T09:30:00+00:00"),
                          "am#BUG-4": ("running", "", "escalate", "2026-11-20T08:00:00+00:00")})
        self.assertEqual(registry["antimurphy#59"]["url"], "https://u/59")
        self.assertEqual(ballet_monitor.read_ready(), {"antimurphy": [{"item": "#7", "number": 7, "type": "Task"}]})
        with ballet_db.reading() as connection:
            running = [row["conductor"] for row in connection.execute("SELECT conductor FROM nodes WHERE ended_at IS NULL ORDER BY conductor")]
        self.assertEqual(running, ["am#BUG-4", "antimurphy#61"])

    def test_les_fichiers_repris_sont_mis_de_cote_et_relancer_ne_fait_rien(self):
        self.old_state()
        self.assertEqual(len(ballet_legacy.run_import()), 4)
        self.assertEqual(sorted(path.name for path in self.state.iterdir() if path.suffix == ".imported"),
                         ["auto_launch_paused.imported", "conductors.json.imported", "maestro.toml.imported", "monitor.json.imported"])
        self.assertEqual(ballet_legacy.run_import(), [])
        self.assertEqual(len(ballet_conductors.read()), 3)

    def test_ouvrir_la_base_ne_reprend_rien(self):
        self.old_state()
        self.assertEqual(ballet_conductors.read(), {})
        self.assertTrue((self.state / "conductors.json").is_file())

    def test_tant_que_l_ancien_etat_attend_les_commandes_refusent(self):
        self.old_state()
        self.assertEqual(sorted(path.name for path in ballet_legacy.pending()),
                         ["auto_launch_paused", "conductors.json", "maestro.toml", "monitor.json"])
        with self.assertRaisesRegex(ballet_legacy.LegacyError, "ballet_legacy.py import"):
            ballet_legacy.refuse_if_pending()
        self.assertEqual(ballet_maestro.main(["ballet_maestro.py", "status"], orca=lambda arguments: "{}"), 1)
        ballet_legacy.run_import()
        self.assertEqual(ballet_legacy.pending(), [])

    def test_une_reprise_qui_echoue_ne_reprend_rien_et_ne_met_rien_de_cote(self):
        self.old_state()
        (self.state / "monitor.json").write_text("{pas du json", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            ballet_legacy.run_import()
        self.assertEqual(ballet_conductors.read(), {})
        self.assertTrue((self.state / "conductors.json").is_file())
        self.assertIn("[lease]", (self.state / "maestro.toml").read_text(encoding="utf-8"))
        self.assertFalse((self.state / "maestro.toml.imported").exists())

    def test_la_commande_se_lance_pour_de_vrai(self):
        """Lancé en script, `ballet_legacy.py` s'importe sans boucle d'imports (les tests, eux, l'importent en module)."""
        import os
        import subprocess
        script = Path(__file__).resolve().parent.parent / "scripts" / "ballet_legacy.py"
        self.old_state()
        done = subprocess.run([sys.executable, str(script), "import"], capture_output=True, text=True,
                              env={**os.environ, "BALLET_HOME": str(self.state)})
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertEqual(done.stdout.count("taken over: "), 4)

    def test_sans_ancien_etat_rien_n_est_repris_ni_ecrit(self):
        ballet_maestro.write_config({"projects": {"antimurphy": {"path": "/p"}}})
        before = (self.state / "maestro.toml").read_text(encoding="utf-8")
        self.assertEqual(ballet_legacy.run_import(), [])
        self.assertEqual((self.state / "maestro.toml").read_text(encoding="utf-8"), before)
        self.assertEqual(sorted(path.name for path in self.state.iterdir() if path.suffix == ".imported"), [])



class BalletLegacyProjectTest(unittest.TestCase):
    """La reprise, une seule fois, du `.ballet/run/` d'un projet."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.state = root / "ballet-home"
        environment = mock.patch.dict("os.environ", {"BALLET_HOME": str(self.state)})
        environment.start()
        self.addCleanup(environment.stop)
        self.home = root / "shop"
        self.run = self.home / ".ballet" / "run"
        self.run.mkdir(parents=True)
        ballet_maestro.add_project("shop", str(self.home))

    def write(self, name, value):
        path = self.run / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")

    def old_run(self):
        self.write("session-3.json", {"item": "#3", "status": "open", "current": "FEAT-001.2", "items": [], "played": []})
        self.write("FEAT-001.2.json", {"id": "FEAT-001.2", "issue": "3", "repo": "app", "status": "open", "session": "#3"})
        self.write("workshop-BUG-4.json", {"item": "BUG-4", "repo": "app", "status": "done"})
        self.write("queue.json", ["#3"])
        entries = [{"at": "2026-11-16T12:00:00+00:00", "rehearsal": "FEAT-001.2", "event": "begin", "detail": {"item": "#3"}},
                   {"at": "2026-11-16T12:00:05+00:00", "rehearsal": "FEAT-001.2", "event": "handoff", "detail": {"role": "dancer", "how": "start"}},
                   {"at": "2026-11-16T12:30:00+00:00", "rehearsal": "FEAT-001.2", "event": "message",
                    "detail": {"from": "dancer", "to": "conductor", "type": "report"}},
                   {"at": "2026-11-16T12:31:00+00:00", "workshop": "BUG-4", "event": "published", "detail": {"issue": "9"}}]
        self.write("journal.jsonl", "\n".join(json.dumps(entry) for entry in entries) + '\n{"at": "2026-11-16T12:3\n')
        self.write("FEAT-001.2/dancer-1.md", "the mission")
        self.write("outbox.md", "a message")

    def test_les_etats_et_le_journal_du_projet_passent_dans_la_base_a_leurs_dates(self):
        self.old_run()
        ballet_legacy.run_import()
        self.assertEqual(ballet_rehearsal.load("FEAT-001.2", self.home).issue, "3")
        self.assertEqual([session.item for session in ballet_rehearsal.open_sessions(self.home)], ["#3"])
        self.assertEqual(ballet_store.load(self.home, "workshop", "BUG-4")["status"], "done")
        entries = ballet_store.journal_of(self.home, "rehearsal", "FEAT-001.2")
        self.assertEqual([(entry["at"], entry["event"]) for entry in entries],
                         [("2026-11-16T12:00:00+00:00", "begin"), ("2026-11-16T12:00:05+00:00", "handoff"), ("2026-11-16T12:30:00+00:00", "message")])
        with ballet_db.reading() as connection:
            turn = connection.execute("SELECT started_at, ended_at, outcome FROM nodes WHERE kind = 'turn'").fetchone()
        self.assertEqual(tuple(turn), ("2026-11-16T12:00:05+00:00", "2026-11-16T12:30:00+00:00", "ok"))

    def test_les_fichiers_de_travail_vont_hors_du_projet_et_le_dossier_est_mis_de_cote(self):
        self.old_run()
        ballet_legacy.run_import()
        work = self.state / "projects" / "shop"
        self.assertEqual(((work / "FEAT-001.2" / "dancer-1.md").read_text(), (work / "outbox.md").read_text()), ("the mission", "a message"))
        self.assertFalse(self.run.exists())
        self.assertTrue((self.home / ".ballet" / "run.imported" / "journal.jsonl").is_file())
        self.assertEqual(ballet_legacy.pending(), [])
        self.assertEqual(ballet_legacy.run_import(), [])

    def test_un_conductor_refuse_de_jouer_tant_que_le_dossier_du_projet_attend(self):
        self.old_run()
        step = ballet_rehearsal.main(["ballet_rehearsal.py", "status"], home=self.home)
        self.assertEqual(step, 0)
        self.assertEqual(ballet_store.all_of(self.home, "session"), [])
        self.assertEqual([path.name for path in ballet_legacy.pending()], ["run"])

    def test_un_home_hors_de_maestro_toml_se_nomme(self):
        self.run.rmdir()
        other = Path(self._tmp.name) / "other"
        (other / ".ballet" / "run").mkdir(parents=True)
        (other / ".ballet" / "run" / "FEAT-009.json").write_text(json.dumps({"id": "FEAT-009", "repo": "x", "status": "done"}), encoding="utf-8")
        self.assertEqual(ballet_legacy.pending(), [])
        ballet_legacy.run_import(homes=[other])
        self.assertEqual(ballet_store.load(other, "rehearsal", "FEAT-009")["status"], "done")

if __name__ == "__main__":
    unittest.main()
