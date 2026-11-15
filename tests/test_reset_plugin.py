import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import reset_plugin  # noqa: E402


class ResetPluginTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.clone = self.root / "ballet"
        self._write(self.clone / "skills" / "dramaturg" / "SKILL.md")
        self._write(self.clone / "templates" / "feature.md")
        self.copy = self.root / "cache" / "ballet" / "0.1.0"
        self.commands = []
        self._patch("CLAUDE_HOME", self.root / "claude")
        self._patch("VIBE_PLUGINS", self.root / "vibe" / "plugins")
        self._patch("_run", self._record)
        self._patch("_installed", lambda command: command == "claude")

    def test_claude_est_desinstalle_puis_reinstalle(self):
        self._register_claude_copy(with_files=True)
        report = reset_plugin.reset_plugin(self.clone)
        self.assertEqual(report, ["✓ claude : réinstallé depuis le clone"])
        self.assertEqual(self.commands[0][:3], ("claude", "plugin", "uninstall"))
        self.assertEqual(self.commands[-1][:3], ("claude", "plugin", "install"))

    def test_une_copie_claude_incomplete_est_signalee(self):
        self._register_claude_copy(with_files=False)
        report = reset_plugin.reset_plugin(self.clone)
        self.assertTrue(report[0].startswith("✗ claude"))
        self.assertIn("templates/feature.md", report[0])

    def test_vibe_recoit_un_lien_vers_le_clone(self):
        self._patch("_installed", lambda command: command == "vibe")
        report = reset_plugin.reset_plugin(self.clone)
        link = self.root / "vibe" / "plugins" / "ballet"
        self.assertEqual(link.resolve(), self.clone.resolve())
        self.assertEqual(report, ["✓ vibe : lien refait vers le clone"])

    def test_un_lien_vibe_deja_bon_n_est_pas_refait(self):
        self._patch("_installed", lambda command: command == "vibe")
        reset_plugin.reset_plugin(self.clone)
        self.assertEqual(reset_plugin.reset_plugin(self.clone), ["✓ vibe : le lien pointe déjà vers le clone"])

    # --- aides ---

    def _register_claude_copy(self, with_files):
        if with_files:
            self._write(self.copy / "skills" / "dramaturg" / "SKILL.md")
            self._write(self.copy / "templates" / "feature.md")
        registry = self.root / "claude" / "installed_plugins.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({"plugins": {"ballet@ballet-local": [{"installPath": str(self.copy)}]}}))

    def _record(self, *command):
        self.commands.append(command)
        return True

    def _patch(self, name, value):
        patcher = mock.patch.object(reset_plugin, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _write(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")


if __name__ == "__main__":
    unittest.main()
