"""Configuration de Ballet : défauts du plugin, surcharges du projet, vérifications.

    python3 ballet_config.py check [dossier-du-projet]   # liste les problèmes
    python3 ballet_config.py show  [dossier-du-projet]   # affiche la config fusionnée
"""

import json
import sys
import tomllib
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
PROJECT_CONFIG = Path(".ballet") / "config.toml"

ROLES = ("dramaturg", "choreographer", "dancer", "critic")
CLIS = ("claude", "grok", "mistral-vibe", "codex", "opencode", "gemini-cli", "kimi")
MERGE_POLICIES = ("trunk", "pr")


class ConfigError(Exception):
    """Le fichier de config est illisible."""


def effective_config(project_dir, plugin_root=PLUGIN_ROOT):
    defaults = _read_toml(Path(plugin_root) / "config.toml")
    overrides = _read_project_overrides(Path(project_dir))
    return _merged(defaults, overrides)


def find_problems(config, plugin_root=PLUGIN_ROOT):
    return (
        _project_problems(config)
        + _repo_problems(config)
        + _rule_problems(config, Path(plugin_root))
        + _role_problems(config)
        + _critic_dancer_problems(config)
        + _threshold_problems(config)
    )


def main(argv):
    command, project_dir = _parse_arguments(argv)
    try:
        config = effective_config(project_dir)
    except ConfigError as error:
        return _fail([str(error)])
    if command == "show":
        print(json.dumps(config, indent=2, ensure_ascii=False))
        return 0
    problems = find_problems(config)
    return _fail(problems) if problems else _succeed()


# --- lecture et fusion ------------------------------------------------------


def _read_toml(path):
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path} : TOML invalide ({error})") from error


def _read_project_overrides(project_dir):
    path = project_dir / PROJECT_CONFIG
    return _read_toml(path) if path.exists() else {}


def _merged(defaults, overrides):
    """Fusion clé par clé : une table se fusionne, toute autre valeur est remplacée."""
    result = dict(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merged(result[key], value)
        else:
            result[key] = value
    return result


# --- vérifications ----------------------------------------------------------


def _project_problems(config):
    project = _table(config, "project")
    if not project.get("specs"):
        return ["[project] specs manquant : lance /ballet:init-project"]
    problems = []
    if not isinstance(project["specs"], str):
        problems.append("[project] specs doit être un texte")
    if project.get("merge") not in MERGE_POLICIES:
        problems.append(f"[project] merge doit valoir {' ou '.join(MERGE_POLICIES)}")
    if not isinstance(project.get("adr"), str) or not project.get("adr"):
        problems.append("[project] adr doit être un chemin de dossier, ex. docs/ADR/")
    if not _is_language_code(project.get("specs_language")):
        problems.append("[project] specs_language doit être un code de langue, ex. en ou fr")
    return problems


def _repo_problems(config):
    repos = _table(config, "repos")
    if not repos:
        return ["aucun repo déclaré : ajoute une section [repos.<nom>] (ou lance /ballet:init-project)"]
    problems = []
    for name, repo in repos.items():
        problems += _single_repo_problems(name, repo, known=repos)
    return problems + _needs_cycle_problems(repos)


def _single_repo_problems(name, repo, known):
    if not isinstance(repo, dict):
        return [f"[repos.{name}] doit être une table"]
    problems = []
    for field in ("path", "proof"):
        if not repo.get(field):
            problems.append(f"[repos.{name}] {field} manquant")
    for needed in repo.get("needs", []):
        if needed not in known:
            problems.append(f"[repos.{name}] needs : repo inconnu « {needed} »")
    return problems


def _needs_cycle_problems(repos):
    needs = {
        name: [n for n in repo.get("needs", []) if n in repos]
        for name, repo in repos.items()
        if isinstance(repo, dict)
    }
    cycle = _find_cycle(needs)
    return [f"cycle dans needs : {' → '.join(cycle)}"] if cycle else []


def _rule_problems(config, plugin_root):
    known = {path.parent.name for path in (plugin_root / "skills").glob("*/SKILL.md")}
    rules = _table(config, "project").get("rules", [])
    return [f"[project] rules : règle inconnue « {rule} »" for rule in rules if rule not in known]


def _role_problems(config):
    roles = _table(config, "roles")
    problems = [f"[roles.{name}] : rôle inconnu" for name in roles if name not in ROLES]
    for role in ROLES:
        settings = roles.get(role)
        if not isinstance(settings, dict) or not settings.get("cli"):
            problems.append(f"[roles.{role}] cli manquant")
        elif settings["cli"] not in CLIS:
            problems.append(f"[roles.{role}] cli inconnu « {settings['cli']} »")
    return problems


def _critic_dancer_problems(config):
    """Critic ≠ Dancer : CLI différents, ou même CLI avec deux modèles explicites différents."""
    roles = _table(config, "roles")
    dancer, critic = roles.get("dancer"), roles.get("critic")
    if not isinstance(dancer, dict) or not isinstance(critic, dict):
        return []
    if dancer.get("cli") != critic.get("cli") or _models_differ(dancer, critic):
        return []
    return ["Critic ≠ Dancer : même CLI sans deux modèles explicites différents"]


def _threshold_problems(config):
    escalation = _table(config, "escalation")
    problems = []
    for key in ("max_round_trips", "max_exchange_rounds", "max_diff_lines"):
        value = escalation.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            problems.append(f"[escalation] {key} doit être un entier positif")
    zones = _table(config, "policy").get("sensitive_zones", [])
    if not isinstance(zones, list) or not all(isinstance(zone, str) for zone in zones):
        problems.append("[policy] sensitive_zones doit être une liste de globs")
    return problems


# --- outils -----------------------------------------------------------------


def _table(config, name):
    value = config.get(name, {})
    return value if isinstance(value, dict) else {}


def _is_language_code(value):
    return isinstance(value, str) and value.isalpha() and value.islower() and len(value) in (2, 3)


def _models_differ(first, second):
    return bool(first.get("model")) and bool(second.get("model")) and first["model"] != second["model"]


def _find_cycle(needs):
    """Renvoie un cycle sous forme de liste de repos, ou None."""
    visiting, done = [], set()

    def visit(name):
        if name in done:
            return None
        if name in visiting:
            return visiting[visiting.index(name):] + [name]
        visiting.append(name)
        for needed in needs.get(name, []):
            cycle = visit(needed)
            if cycle:
                return cycle
        visiting.pop()
        done.add(name)
        return None

    for name in needs:
        cycle = visit(name)
        if cycle:
            return cycle
    return None


def _parse_arguments(argv):
    command = argv[1] if len(argv) > 1 else "check"
    project_dir = argv[2] if len(argv) > 2 else "."
    if command not in ("check", "show"):
        raise SystemExit(__doc__)
    return command, project_dir


def _fail(problems):
    for problem in problems:
        print(f"✗ {problem}", file=sys.stderr)
    return 1


def _succeed():
    print("✓ configuration valide")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
