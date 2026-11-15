"""Amorce un projet pour Ballet, dans son home.

    python3 init_project.py <dossier> --specs specs/ --proof "make test" [--repo nom] [--rules tdd,bdd]

Ne remplace jamais un fichier existant : il le signale.
"""

import argparse
import re
import sys
from pathlib import Path

import ballet_config

DEFAULT_RULES = ("tdd", "bdd", "ddd", "clean-code")

CONFIG_TEMPLATE = """\
# Profil du projet pour Ballet. Les surcharges de routage vont ici (voir config.toml du plugin).

[project]
specs = {specs}
rules = [{rules}]

[repos.{repo}]
path = "."
proof = {proof}
"""

AGENTS_TEMPLATE = """\
# {name} — règles du projet

Ce projet suit la méthode Ballet. Son profil est dans `.ballet/config.toml`.

Avant de coder, charge les règles communes listées dans `[project] rules` du profil
(skills `ballet:<règle>`, par exemple `ballet:tdd`).
Une règle écrite dans ce fichier l'emporte sur une règle commune.

## Domaine

(à compléter : glossaire, invariants, décisions d'architecture)
"""


def init_project(project_dir, specs, proof, repo=None, rules=DEFAULT_RULES):
    """Crée ce qui manque ; renvoie ce qui a été créé et ce qui existait déjà."""
    project_dir = Path(project_dir).resolve()
    repo = repo or _repo_name(project_dir)
    report = {"created": [], "kept": []}
    _write_config(project_dir, specs, proof, repo, rules, report)
    _write_agents(project_dir, report)
    _write_claude(project_dir, report)
    _link_agent_skills(project_dir, report)
    return report


def main(argv):
    arguments = _parse(argv)
    report = init_project(
        arguments.project_dir, arguments.specs, arguments.proof, arguments.repo, arguments.rules
    )
    _print(report)
    return _check(arguments.project_dir)


# --- étapes -----------------------------------------------------------------


def _write_config(project_dir, specs, proof, repo, rules, report):
    text = CONFIG_TEMPLATE.format(
        specs=_toml_string(specs),
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
    parser.add_argument("--proof", required=True, help="commande de preuve, ex. make test")
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
