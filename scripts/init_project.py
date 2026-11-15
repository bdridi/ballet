"""Amorce un projet pour Ballet, dans son home.

    python3 init_project.py <dossier> --specs specs/ --proof "make test" [--specs-language fr] [--repo nom] [--rules tdd,bdd]

Ne remplace jamais un fichier existant : il le signale.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import ballet_config

DEFAULT_RULES = ("tdd", "bdd", "ddd", "clean-code")

CONFIG_TEMPLATE = """\
# Ballet project profile. Overrides of the plugin defaults go here (see the plugin's config.toml).

[project]
specs = {specs}
specs_language = {specs_language}
rules = [{rules}]

[repos.{repo}]
path = "."
proof = {proof}
"""

AGENTS_TEMPLATE = """\
# {name} — project rules

This project follows the Ballet method. Its profile is in `.ballet/config.toml`.

Before coding, load the common rules listed in `[project] rules` of the profile
(skills `ballet:<rule>`, e.g. `ballet:tdd`).
A rule written in this file wins over a common rule.

## Domain

(to fill in: invariants, architecture decisions; the domain words live in the glossary of the specs space)
"""

RESET_SKILL_TEMPLATE = """\
---
name: reset-ballet
description: Reinstalls the Ballet plugin from its clone, for Claude, Vibe and Grok. Run it after each change to the plugin, or when a ballet skill looks outdated.
---

# reset-ballet

Run the script of the Ballet clone (never the one of an installed copy, which may be outdated):

```sh
python3 "{script}"
```

Report each CLI's line to the Director. Remind them to restart open sessions:
they keep the plugin they loaded at startup.

If the path no longer exists, the clone has moved: delete this skill (`.claude/skills/reset-ballet/`),
then run `/ballet:init-project` again from the new clone.
"""

PLUGIN_NAME = "ballet"
CLAUDE_MARKETPLACES = Path.home() / ".claude" / "plugins" / "known_marketplaces.json"


def init_project(project_dir, specs, proof, repo=None, rules=DEFAULT_RULES, specs_language="en"):
    """Crée ce qui manque ; renvoie ce qui a été créé et ce qui existait déjà."""
    project_dir = Path(project_dir).resolve()
    repo = repo or _repo_name(project_dir)
    report = {"created": [], "kept": []}
    _write_config(project_dir, specs, proof, repo, rules, specs_language, report)
    _write_agents(project_dir, report)
    _write_claude(project_dir, report)
    _link_agent_skills(project_dir, report)
    _write_reset_skill(project_dir, report)
    return report


def main(argv):
    arguments = _parse(argv)
    report = init_project(
        arguments.project_dir,
        arguments.specs,
        arguments.proof,
        arguments.repo,
        arguments.rules,
        arguments.specs_language,
    )
    _print(report)
    return _check(arguments.project_dir)


# --- étapes -----------------------------------------------------------------


def _write_config(project_dir, specs, proof, repo, rules, specs_language, report):
    text = CONFIG_TEMPLATE.format(
        specs=_toml_string(specs),
        specs_language=_toml_string(specs_language),
        proof=_toml_string(proof),
        repo=repo,
        rules=", ".join(_toml_string(rule) for rule in rules),
    )
    _write_unless_exists(project_dir / ballet_config.PROJECT_CONFIG, text, report)


def _write_agents(project_dir, report):
    text = AGENTS_TEMPLATE.format(name=project_dir.name)
    _write_unless_exists(project_dir / "AGENTS.md", text, report)


def _write_claude(project_dir, report):
    _write_unless_exists(project_dir / "CLAUDE.md", "@AGENTS.md\n", report)


def _link_agent_skills(project_dir, report):
    skills = project_dir / ".claude" / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    _write_unless_exists(skills / ".gitkeep", "", report)  # git ne suit pas un dossier vide
    link = project_dir / ".agents" / "skills"
    if link.is_symlink() or link.exists():
        report["kept"].append(link)
        return
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(Path("..") / ".claude" / "skills")
    report["created"].append(link)


def _write_reset_skill(project_dir, report):
    script = _plugin_clone() / "scripts" / "reset_plugin.py"
    text = RESET_SKILL_TEMPLATE.format(script=script)
    _write_unless_exists(project_dir / ".claude" / "skills" / "reset-ballet" / "SKILL.md", text, report)


# --- outils -----------------------------------------------------------------


def _plugin_clone():
    """Le clone de Ballet : la marketplace locale de Claude qui le sert, sinon le dossier de ce script.

    Ce script peut tourner depuis la copie que Claude garde en cache : il ne faut pas la désigner.
    """
    for path in _local_marketplaces():
        if _is_ballet(path):
            return path
    return Path(__file__).resolve().parent.parent


def _local_marketplaces():
    if not CLAUDE_MARKETPLACES.exists():
        return []
    marketplaces = json.loads(CLAUDE_MARKETPLACES.read_text()).values()
    return [Path(m["source"]["path"]) for m in marketplaces if m["source"].get("source") == "directory"]


def _is_ballet(path):
    manifest = path / ".claude-plugin" / "plugin.json"
    return manifest.exists() and json.loads(manifest.read_text()).get("name") == PLUGIN_NAME


def _write_unless_exists(path, text, report):
    if path.exists():
        report["kept"].append(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    report["created"].append(path)


def _toml_string(text):
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _repo_name(project_dir):
    return re.sub(r"[^a-z0-9_-]+", "-", project_dir.name.lower()).strip("-") or "app"


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project_dir")
    parser.add_argument("--specs", required=True, help="espace des specs, ex. specs/")
    parser.add_argument("--proof", required=True, help="commande de preuve, ex. make test")
    parser.add_argument("--specs-language", default="en", help="langue des specs (défaut : en)")
    parser.add_argument("--repo", help="nom du repo (défaut : nom du dossier)")
    parser.add_argument("--rules", type=_split_rules, default=DEFAULT_RULES)
    return parser.parse_args(argv[1:])


def _split_rules(text):
    return tuple(rule for rule in text.split(",") if rule)


def _print(report):
    for path in report["created"]:
        print(f"créé       {path}")
    for path in report["kept"]:
        print(f"existe déjà {path} (non modifié)")


def _check(project_dir):
    config = ballet_config.effective_config(project_dir)
    problems = ballet_config.find_problems(config)
    for problem in problems:
        print(f"✗ {problem}", file=sys.stderr)
    if not problems:
        print("✓ configuration valide")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
