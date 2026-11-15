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
        self.copy = self.root / "cache" / "ballet" / "0.3.0"
        self.claude_skills = self.root / "claude" / "skills"
        self.vibe = self.root / "vibe"
        self.commands = []
        self._patch("CLAUDE_PLUGINS", self.root / "claude" / "plugins")
        self._patch("CLAUDE_SKILLS", self.claude_skills)
        self._patch("VIBE_HOME", self.vibe)
        self._patch("_run", self._record)
        self._only("claude")

    # --- claude

    def test_claude_est_desinstalle_puis_reinstalle(self):
        self._register_claude_copy(with_files=True)
        report = reset_plugin.reset_plugin(self.clone)
        self.assertEqual(report[0], "✓ claude : réinstallé depuis le clone")
        self.assertEqual(self.commands[0][:3], ("claude", "plugin", "uninstall"))
        self.assertEqual(self.commands[-1][:3], ("claude", "plugin", "install"))

    def test_une_copie_claude_incomplete_est_signalee(self):
        self._register_claude_copy(with_files=False)
        report = reset_plugin.reset_plugin(self.clone)
        self.assertTrue(report[0].startswith("✗ claude"))
        self.assertIn("templates/feature.md", report[0])

    def test_le_skill_user_reset_ballet_lance_le_script_du_clone(self):
        self._register_claude_copy(with_files=True)
        reset_plugin.reset_plugin(self.clone)
        skill = (self.claude_skills / "reset-ballet" / "SKILL.md").read_text()
        self.assertIn(str(self.clone.resolve() / "scripts" / "reset_plugin.py"), skill)

    def test_le_skill_user_est_reecrit_a_chaque_passage(self):
        self._register_claude_copy(with_files=True)
        self._write(self.claude_skills / "reset-ballet" / "SKILL.md")
        reset_plugin.reset_plugin(self.clone)
        self.assertIn("name: reset-ballet", (self.claude_skills / "reset-ballet" / "SKILL.md").read_text())

    # --- vibe

    def test_vibe_recoit_le_plugin_et_les_skills_user_par_des_liens(self):
        self._only("vibe")
        reset_plugin.reset_plugin(self.clone)
        self.assertEqual((self.vibe / "plugins" / "ballet").resolve(), self.clone.resolve())
        self.assertEqual((self.vibe / "skills").resolve(), self.claude_skills.resolve())

    def test_des_liens_vibe_deja_bons_ne_sont_pas_refaits(self):
        self._only("vibe")
        reset_plugin.reset_plugin(self.clone)
        report = reset_plugin.reset_plugin(self.clone)
        self.assertTrue(all("déjà" in line for line in report), report)

    def test_un_dossier_vibe_skills_non_vide_n_est_jamais_ecrase(self):
        self._only("vibe")
        self._write(self.vibe / "skills" / "mine" / "SKILL.md")
        report = reset_plugin.reset_plugin(self.clone)
        self.assertTrue((self.vibe / "skills" / "mine" / "SKILL.md").exists())
        self.assertIn("✗ vibe : skills user", report[1])

    def test_un_dossier_vibe_skills_vide_est_remplace_par_le_lien(self):
        self._only("vibe")
        (self.vibe / "skills").mkdir(parents=True)
        reset_plugin.reset_plugin(self.clone)
        self.assertTrue((self.vibe / "skills").is_symlink())

    # --- grok

    def test_grok_absent_est_installe_depuis_le_clone(self):
        self._only("grok")
        self._patch("_run", lambda *command: self._record(*command) and command[2] != "update")
        self.assertEqual(reset_plugin.reset_plugin(self.clone), ["✓ grok : installé depuis le clone"])

    # --- aides ---

    def _only(self, cli):
        self._patch("_installed", lambda command: command == cli)

    def _register_claude_copy(self, with_files):
        if with_files:
            self._write(self.copy / "skills" / "dramaturg" / "SKILL.md")
            self._write(self.copy / "templates" / "feature.md")
        registry = self.root / "claude" / "plugins" / "installed_plugins.json"
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
