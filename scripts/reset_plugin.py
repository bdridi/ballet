"""Installe ou réinstalle le plugin Ballet depuis son clone, pour chaque CLI présent sur la machine.

    python3 reset_plugin.py

À lancer une première fois pour installer, puis après chaque évolution du plugin
(ou `/reset-ballet`, le skill user qu'il pose pour Claude). Claude travaille sur une copie du plugin
(son cache), qu'il ne rafraîchit pas tant que la version ne change pas : on désinstalle
et on réinstalle. Vibe lit le clone par un lien, Grok le lit en local.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN = "ballet"
MARKETPLACE = "ballet-local"
CLAUDE_PLUGINS = Path.home() / ".claude" / "plugins"
CLAUDE_SKILLS = Path.home() / ".claude" / "skills"
VIBE_HOME = Path.home() / ".vibe"

RESET_SKILL = """\
---
name: reset-ballet
description: Reinstalls the Ballet plugin from its clone, for Claude, Vibe and Grok. Run it after each change to the plugin, or when a ballet skill looks outdated.
---

# reset-ballet

Run the script of the Ballet clone (never the one of an installed copy, which may be outdated):

```sh
python3 "{script}"
```

Report each line to the Director. Remind them to restart open sessions:
they keep the plugin they loaded at startup.

This skill is written by that script, at each run: do not edit it by hand.
"""


def reset_plugin(source):
    """Remet chaque CLI installé sur le clone `source` ; renvoie une ligne de bilan par étape."""
    source = Path(source).resolve()
    report = []
    if _installed("claude"):
        report.append(_reset_claude(source))
        report.append(_write_reset_skill(source))
    if _installed("vibe") or VIBE_HOME.exists():
        report.append(_link_vibe_plugin(source))
    if _installed("grok"):
        report.append(_reset_grok(source))
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


def _write_reset_skill(source):
    skill = CLAUDE_SKILLS / "reset-ballet" / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(RESET_SKILL.format(script=source / "scripts" / "reset_plugin.py"), encoding="utf-8")
    return f"✓ skill user reset-ballet : {skill}"


def _link_vibe_plugin(source):
    return _link(VIBE_HOME / "plugins" / PLUGIN, source, "vibe : plugin")


def _reset_grok(source):
    if _run("grok", "plugin", "update", PLUGIN):
        return "✓ grok : mis à jour"
    if _run("grok", "plugin", "install", str(source), "--trust"):
        return "✓ grok : installé depuis le clone"
    return "✗ grok : ni mise à jour ni installation (voir `grok plugin list`)"


# --- outils -----------------------------------------------------------------


def _link(link, target, label):
    """Fait de `link` un lien vers `target`, sans jamais écraser un dossier qui a du contenu."""
    if link.is_symlink() and link.resolve() == target.resolve():
        return f"✓ {label} : le lien pointe déjà vers {target}"
    if link.is_dir() and not link.is_symlink():
        if any(link.iterdir()):
            return f"✗ {label} : {link} est un vrai dossier non vide ; à fusionner à la main"
        link.rmdir()
    link.unlink(missing_ok=True)
    link.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    return f"✓ {label} : lien {link} → {target}"


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
    registry = CLAUDE_PLUGINS / "installed_plugins.json"
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
