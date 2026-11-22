import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ballet_conductors  # noqa: E402
import ballet_maestro  # noqa: E402
import ballet_runtime  # noqa: E402
import ballet_upgrade  # noqa: E402
from test_ballet_maestro import FakeOrca  # noqa: E402

OLD_TOML = """[mailbox]
terminal = "term_box"
run = "run_box"

[lease]
owner = "old-owner"
pid = 4242
renewed = "2026-11-22T16:50:33+00:00"
session = "s-old"

[monitor]
terminal = "term_mon"

[maestro]
terminal = "term_mae"

[projects.shop]
path = "{home}"
"""


class ClosingOrca(FakeOrca):
    """Comme Orca : un terminal fermé n'est plus dans la liste."""

    def __call__(self, arguments):
        if arguments[:2] == ["terminal", "close"]:
            self.terminals.remove(arguments[arguments.index("--terminal") + 1])
        return super().__call__(arguments)


class BalletUpgradeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.state = root / "ballet-home"
        self.state.mkdir()
        self.home = root / "shop"
        self.home.mkdir()
        environment = mock.patch.dict("os.environ", {"BALLET_HOME": str(self.state), "BALLET_MAESTRO_COMMAND": "true"})
        environment.start()
        self.addCleanup(environment.stop)
        self.orca = ClosingOrca()
        self.reinstalled = []
        self.stopped_waits = []
        stop = mock.patch.object(ballet_maestro, "stop_the_wait", side_effect=self.stopped_waits.append)
        stop.start()
        self.addCleanup(stop.stop)

    def reinstall(self):
        self.reinstalled.append(True)
        return "✓ claude: reinstalled"

    def upgrade(self, reinstall=None):
        return ballet_upgrade.upgrade(self.orca, reinstall=reinstall or self.reinstall)

    def closed(self):
        return [command[command.index("--terminal") + 1] for command in self.orca.ran("terminal", "close")]

    def test_depuis_une_ancienne_version_tout_est_arrete_repris_puis_redemarre(self):
        (self.state / "maestro.toml").write_text(OLD_TOML.format(home=self.home), encoding="utf-8")
        self.orca.terminals += ["term_box", "term_mon", "term_mae"]
        report = self.upgrade()
        self.assertTrue(all(line.startswith("✓") for line in report), report)
        self.assertEqual((self.closed(), self.stopped_waits, self.reinstalled), (["term_mon", "term_mae"], [4242], [True]))
        runtime = ballet_runtime.read()
        self.assertEqual((runtime["mailbox_terminal"], runtime["mailbox_run"]), ("term_box", "run_box"))
        self.assertEqual(runtime["lease_owner"], "")
        self.assertEqual((runtime["monitor_terminal"], runtime["maestro_terminal"]), ("term_1", "term_2"))
        self.assertEqual(sorted(self.orca.terminals), ["term_1", "term_2", "term_box"])
        self.assertTrue((self.state / "maestro.toml.imported").is_file())

    def test_sur_la_base_les_terminaux_notes_sont_remplaces(self):
        ballet_runtime.update(mailbox_terminal="term_box", mailbox_run="run_box", monitor_terminal="term_mon",
                              maestro_terminal="term_mae", lease_owner="abc", lease_pid=77)
        self.orca.terminals += ["term_box", "term_mon", "term_mae"]
        report = self.upgrade()
        self.assertIn("✓ take over the older state: nothing to take over", report)
        self.assertEqual((self.closed(), self.stopped_waits), (["term_mon", "term_mae"], [77]))
        self.assertEqual(ballet_runtime.read()["maestro_terminal"], "term_2")

    def test_un_redemarrage_interrompu_est_ferme_et_sa_pause_retiree(self):
        ballet_runtime.update(mailbox_terminal="term_box", mailbox_run="run_box", maestro_terminal="term_mae",
                              restart_terminal="term_rst", restart_owns_pause=True, paused_at="2026-11-22T10:00:00+00:00")
        self.orca.terminals += ["term_box", "term_mae", "term_rst"]
        self.upgrade()
        self.assertIn("term_rst", self.closed())
        runtime = ballet_runtime.read()
        self.assertEqual((runtime["restart_terminal"], runtime["paused_at"]), ("", ""))

    def test_les_conductors_qui_tournent_ne_sont_pas_touches(self):
        ballet_runtime.update(mailbox_terminal="term_box", mailbox_run="run_box")
        ballet_conductors.record_launch("shop#12", "shop", "12", "rehearsal", "term_c")
        self.orca.terminals += ["term_box", "term_c"]
        self.upgrade()
        self.assertNotIn("term_c", self.closed())
        self.assertEqual(ballet_conductors.read()["shop#12"]["state"], "running")

    def test_une_reinstallation_ratee_est_dite_et_le_reste_se_fait(self):
        ballet_runtime.update(mailbox_terminal="term_box", mailbox_run="run_box")
        self.orca.terminals.append("term_box")

        def broken():
            raise ballet_maestro.MaestroError("✗ claude: the installed copy lacks scripts/ballet_upgrade.py")
        report = self.upgrade(reinstall=broken)
        self.assertTrue(any(line.startswith("✗ reinstall the plugin: ") for line in report))
        self.assertTrue(report[-1].startswith("✓ start Maestro: maestro created"))

    def test_lance_depuis_le_terminal_de_maestro_il_ne_fait_rien(self):
        ballet_runtime.update(mailbox_terminal="term_box", mailbox_run="run_box", maestro_terminal="term_mae")
        self.orca.terminals += ["term_box", "term_mae"]
        with mock.patch.dict("os.environ", {"ORCA_TERMINAL_HANDLE": "term_mae"}):
            with self.assertRaisesRegex(ballet_maestro.MaestroError, "from another session"):
                self.upgrade()
        self.assertEqual((self.closed(), self.reinstalled), ([], []))

    def test_la_ligne_de_commande_sort_avec_1_sur_une_etape_ratee(self):
        self.orca.unreachable = True
        with mock.patch.object(ballet_upgrade, "_reinstall", self.reinstall), redirect_stdout(io.StringIO()) as out:
            code = ballet_upgrade.main(["ballet_upgrade.py"], orca=self.orca)
        self.assertEqual(code, 1)
        self.assertIn("✗ start the Monitor", out.getvalue())


if __name__ == "__main__":
    unittest.main()
