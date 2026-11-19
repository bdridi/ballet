"""Amorce un projet pour Ballet, dans son home.

    python3 init_project.py <dossier> --specs specs/ --proof "make test" [--specs-language fr] [--repo nom] [--rules tdd,bdd] [--no-github]

Ne remplace jamais un fichier existant : il le signale. Seule exception, le `.gitignore` du projet,
complété d'une ligne qui ignore l'état des Rehearsals (`.ballet/run/`).
Prépare ensuite, chez le propriétaire du repo GitHub, les types et les champs d'issue dont vit la file
(`ballet_planning.py`), sauf avec `--no-github`.
"""

import argparse
import re
import sys
from pathlib import Path

import ballet_config
import ballet_planning

DEFAULT_RULES = ("tdd", "bdd", "ddd", "clean-code")
RUN_STATE_IGNORE = ".ballet/run/"

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

(to fill in: invariants; the domain words live in the glossary of the specs space)

## Technical rules

(set by the Choreographer, after the Director's yes: conventions every Dancer follows, each pointing to its ADR when there is one)
"""


def init_project(project_dir, specs, proof, repo=None, rules=DEFAULT_RULES, specs_language="en"):
    """Crée ce qui manque ; renvoie ce qui a été créé, complété, et ce qui existait déjà."""
    project_dir = Path(project_dir).resolve()
    repo = repo or _repo_name(project_dir)
    report = {"created": [], "updated": [], "kept": []}
    _write_config(project_dir, specs, proof, repo, rules, specs_language, report)
    _write_agents(project_dir, report)
    _write_claude(project_dir, report)
    _link_agent_skills(project_dir, report)
    _ignore_run_state(project_dir, report)
    return report


def main(argv, prepare_planning=ballet_planning.prepare):
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
    config_status = _check(arguments.project_dir)
    planning_status = 0 if arguments.no_github else _prepare_github(arguments.project_dir, prepare_planning)
    return config_status or planning_status


def _prepare_github(project_dir, prepare_planning):
    """Les types et les champs d'issue de la file, chez le propriétaire du repo ; un refus n'annule pas les fichiers."""
    try:
        ballet_planning.print_report(prepare_planning(project_dir))
    except ballet_planning.PlanningError as error:
        print(f"✗ GitHub planning: {error}", file=sys.stderr)
        return 1
    return 0


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


def _ignore_run_state(project_dir, report):
    """L'état et le journal des Rehearsals sont locaux : git ne les suit jamais."""
    ignore = project_dir / ".gitignore"
    if not ignore.exists():
        ignore.write_text(RUN_STATE_IGNORE + "\n", encoding="utf-8")
        report["created"].append(ignore)
        return
    text = ignore.read_text(encoding="utf-8")
    if RUN_STATE_IGNORE in text.splitlines():
        report["kept"].append(ignore)
        return
    separator = "" if text.endswith("\n") or not text else "\n"
    ignore.write_text(f"{text}{separator}{RUN_STATE_IGNORE}\n", encoding="utf-8")
    report["updated"].append(ignore)


# --- outils -----------------------------------------------------------------


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
    parser.add_argument("--proof", required=True, help="proof command, e.g. make test")
    parser.add_argument("--specs-language", default="en", help="specs language (default: en)")
    parser.add_argument("--repo", help="repo name (default: folder name)")
    parser.add_argument("--rules", type=_split_rules, default=DEFAULT_RULES)
    parser.add_argument("--no-github", action="store_true", help="skip the GitHub issue types and fields")
    return parser.parse_args(argv[1:])


def _split_rules(text):
    return tuple(rule for rule in text.split(",") if rule)


def _print(report):
    for path in report["created"]:
        print(f"created        {path}")
    for path in report["updated"]:
        print(f"completed      {path} (line {RUN_STATE_IGNORE} added)")
    for path in report["kept"]:
        print(f"already exists {path} (unchanged)")


def _check(project_dir):
    config = ballet_config.effective_config(project_dir)
    problems = ballet_config.find_problems(config)
    for problem in problems:
        print(f"✗ {problem}", file=sys.stderr)
    if not problems:
        print("✓ valid configuration")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
