"""Les versions de Ballet (OPP-90) : celle d'un plugin, celle que Claude Code a installée, ce que la Scène en dit.

Maestro et le Monitor sont de longs processus : ils gardent la version du plugin qu'ils ont chargée au démarrage, même
quand le plugin est réinstallé sans `/ballet:setup upgrade`. Chacun note donc la sienne dans la base en démarrant
(`running`, lue dans le `plugin.json` du plugin dont le script fait partie) ; la Scène la compare à la version installée.

`installed` lit là où Claude Code garde le plugin : `installed_plugins.json` (sa version, sinon le `plugin.json` du dossier
installé) dans son dossier (`CLAUDE_CONFIG_DIR`, sinon `~/.claude`) ; sans installation connue, le clone de Ballet que
`reset_plugin.py` installe. Une version qui ne se lit pas est `""` : jamais une erreur.
"""

import json
from pathlib import Path

import ballet_context
import reset_plugin

PLUGIN_JSON = Path(".claude-plugin") / "plugin.json"
UPGRADE = "run /ballet:setup upgrade"


def running(plugin=None):
    """La version du plugin dont ce script fait partie (ou du dossier `plugin`), lue dans son `plugin.json`."""
    return _version_in(plugin or _own_plugin())


def installed(clone=None):
    """La version du plugin installé par Claude Code ; celle du clone sans installation connue ; `""` si rien ne se lit."""
    install = _claude_install()
    return install.get("version") or _version_in(install.get("installPath")) or _version_in(clone or _own_plugin())


def stale_note(role, version, installed_version):
    """Ce que la Scène dit d'un processus qui tourne dans une autre version que l'installée ; `""` quand il n'y a rien à dire.
    Une version inconnue (un processus qui n'a rien noté) n'est pas une version égale."""
    if not installed_version or version == installed_version:
        return ""
    return f"{role} {version or 'version unknown'}, installed {installed_version} : {UPGRADE}"


def _own_plugin():
    return Path(__file__).resolve().parent.parent


def _claude_install():
    """L'installation de Ballet notée par Claude Code (la première) ; vide sans registre lisible ni installation."""
    registry = ballet_context.claude_home() / "plugins" / "installed_plugins.json"
    try:
        installs = json.loads(registry.read_text(encoding="utf-8"))["plugins"][f"{reset_plugin.PLUGIN}@{reset_plugin.MARKETPLACE}"]
        return installs[0] if installs and isinstance(installs[0], dict) else {}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def _version_in(plugin):
    """La version du `plugin.json` d'un dossier de plugin ; vide sans dossier, sans fichier ou s'il est illisible."""
    if not plugin:
        return ""
    try:
        return str(json.loads((Path(plugin) / PLUGIN_JSON).read_text(encoding="utf-8")).get("version") or "")
    except (OSError, ValueError, AttributeError):
        return ""
