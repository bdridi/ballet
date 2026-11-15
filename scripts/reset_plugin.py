"""Réinstalle le plugin Ballet depuis son clone, pour chaque CLI présent sur la machine.

    python3 reset_plugin.py

À lancer après chaque évolution du plugin. Claude travaille sur une copie du plugin
(son cache), qu'il ne rafraîchit pas tant que la version ne change pas : on désinstalle
et on réinstalle. Vibe lit le clone par un lien, Grok le lit en local : on vérifie.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN = "ballet"
MARKETPLACE = "ballet-local"
CLAUDE_HOME = Path.home() / ".claude" / "plugins"
VIBE_PLUGINS = Path.home() / ".vibe" / "plugins"


def reset_plugin(source):
    """Remet chaque CLI installé sur le clone `source` ; renvoie une ligne de bilan par CLI."""
    source = Path(source).resolve()
    report = []
    if _installed("claude"):
        report.append(_reset_claude(source))
    if _installed("vibe") or VIBE_PLUGINS.parent.exists():
        report.append(_link_vibe(source))
    if _installed("grok"):
        report.append(_update_grok())
    return report


def main(argv):
    report = reset_plugin(_clone_dir())
    for line in report:
        print(line)
    if not report:
        print("✗ aucun CLI trouvé (claude, vibe, grok)", file=sys.stderr)
        return 1
    print("Redémarre les sessions ouvertes pour qu'elles chargent le plugin à jour.")
    return 1 if any(line.startswith("✗") for line in report) else 0


# --- étapes -----------------------------------------------------------------


def _reset_claude(source):
    _run("claude", "plugin", "uninstall", f"{PLUGIN}@{MARKETPLACE}")
    if not _run("claude", "plugin", "marketplace", "update", MARKETPLACE):
        _run("claude", "plugin", "marketplace", "add", str(source))
    if not _run("claude", "plugin", "install", f"{PLUGIN}@{MARKETPLACE}"):
        return "✗ claude : l'installation a échoué (voir `claude plugin list`)"
    missing = _missing_in_claude_copy(source)
    if missing:
        return f"✗ claude : la copie installée n'a pas {', '.join(missing)}"
    return "✓ claude : réinstallé depuis le clone"


def _link_vibe(source):
    link = VIBE_PLUGINS / PLUGIN
    if link.is_symlink() and link.resolve() == source:
        return "✓ vibe : le lien pointe déjà vers le clone"
    if link.exists() and not link.is_symlink():
        return f"✗ vibe : {link} est un vrai dossier, pas un lien ; à retirer à la main"
    link.unlink(missing_ok=True)
    VIBE_PLUGINS.mkdir(parents=True, exist_ok=True)
    link.symlink_to(source)
    return "✓ vibe : lien refait vers le clone"


def _update_grok():
    if _run("grok", "plugin", "update", PLUGIN):
        return "✓ grok : mis à jour"
    return "✗ grok : la mise à jour a échoué (voir `grok plugin list`)"


# --- outils -----------------------------------------------------------------


def _missing_in_claude_copy(source):
    """Ce que le clone livre (skills, modèles, scripts) et que la copie de Claude n'a pas."""
    copy = _claude_install_path()
    if copy is None:
        return ["d'installation"]
    expected = [path.relative_to(source) for path in _delivered(source)]
    return [str(path) for path in expected if not (copy / path).exists()]


def _delivered(source):
    for folder in ("skills", "templates", "scripts"):
        root = source / folder
        if root.exists():
            yield from (path for path in root.rglob("*") if path.is_file() and "__pycache__" not in path.parts)


def _claude_install_path():
    registry = CLAUDE_HOME / "installed_plugins.json"
    if not registry.exists():
        return None
    installs = json.loads(registry.read_text()).get("plugins", {}).get(f"{PLUGIN}@{MARKETPLACE}", [])
    return Path(installs[0]["installPath"]) if installs else None


def _installed(command):
    return shutil.which(command) is not None


def _run(*command):
    """Lance une commande ; renvoie vrai si elle a réussi. Son bavardage n'est pas affiché."""
    return subprocess.run(command, capture_output=True, text=True).returncode == 0


def _clone_dir():
    return Path(__file__).resolve().parent.parent


if __name__ == "__main__":
    sys.exit(main(sys.argv))
