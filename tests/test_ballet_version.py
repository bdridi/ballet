import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_version  # noqa: E402


class BalletVersionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.claude = self.root / "claude"
        environment = mock.patch.dict("os.environ", {"CLAUDE_CONFIG_DIR": str(self.claude)})
        environment.start()
        self.addCleanup(environment.stop)

    def plugin_at(self, folder, version):
        (folder / ".claude-plugin").mkdir(parents=True, exist_ok=True)
        (folder / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "ballet", "version": version}), encoding="utf-8")
        return folder

    def register(self, installs):
        registry = self.claude / "plugins" / "installed_plugins.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({"version": 2, "plugins": {"ballet@ballet-local": installs}}), encoding="utf-8")

    # --- la version du plugin dont le script fait partie ---

    def test_la_version_qui_tourne_est_celle_du_plugin_json_du_plugin(self):
        self.assertEqual(ballet_version.running(self.plugin_at(self.root / "plugin", "0.48.0")), "0.48.0")

    def test_la_version_qui_tourne_du_depot_est_celle_de_son_plugin_json(self):
        clone = Path(ballet_version.__file__).resolve().parent.parent
        expected = json.loads((clone / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
        self.assertEqual(ballet_version.running(), expected)

    def test_un_plugin_json_absent_ou_illisible_donne_une_version_vide(self):
        (self.root / "none").mkdir()
        broken = self.plugin_at(self.root / "broken", "0.1.0")
        (broken / ".claude-plugin" / "plugin.json").write_text("{", encoding="utf-8")
        self.assertEqual((ballet_version.running(self.root / "none"), ballet_version.running(broken)), ("", ""))

    # --- la version installée, là où Claude Code garde le plugin ---

    def test_la_version_installee_est_celle_du_registre_de_claude_code(self):
        self.register([{"scope": "user", "installPath": str(self.root / "cache" / "0.45.0"), "version": "0.45.0"}])
        self.assertEqual(ballet_version.installed(), "0.45.0")

    def test_sans_version_au_registre_elle_vient_du_plugin_json_du_dossier_installe(self):
        installed = self.plugin_at(self.root / "cache" / "0.46.0", "0.46.0")
        self.register([{"scope": "user", "installPath": str(installed)}])
        self.assertEqual(ballet_version.installed(), "0.46.0")

    def test_sans_installation_connue_elle_est_celle_du_clone(self):
        clone = self.plugin_at(self.root / "clone", "0.47.0")
        self.assertEqual(ballet_version.installed(clone=clone), "0.47.0")

    def test_un_registre_illisible_ou_sans_ballet_retombe_sur_le_clone(self):
        clone = self.plugin_at(self.root / "clone", "0.47.0")
        (self.claude / "plugins").mkdir(parents=True)
        (self.claude / "plugins" / "installed_plugins.json").write_text("not json", encoding="utf-8")
        self.assertEqual(ballet_version.installed(clone=clone), "0.47.0")
        self.register([])
        self.assertEqual(ballet_version.installed(clone=clone), "0.47.0")

    # --- ce que la Scène dit d'une version qui tourne ---

    def test_une_version_qui_tourne_comme_l_installee_ne_dit_rien(self):
        self.assertEqual(ballet_version.stale_note("Monitor", "0.47.0", "0.47.0"), "")

    def test_une_version_plus_ancienne_dit_de_lancer_l_upgrade(self):
        self.assertEqual(ballet_version.stale_note("Monitor", "0.45.0", "0.47.0"),
                         "Monitor 0.45.0, installed 0.47.0 : run /ballet:setup upgrade")

    def test_une_version_inconnue_est_dite_inconnue_pas_egale(self):
        self.assertEqual(ballet_version.stale_note("Maestro", "", "0.47.0"),
                         "Maestro version unknown, installed 0.47.0 : run /ballet:setup upgrade")

    def test_sans_version_installee_connue_rien_n_est_compare(self):
        self.assertEqual(ballet_version.stale_note("Maestro", "0.45.0", ""), "")


if __name__ == "__main__":
    unittest.main()
