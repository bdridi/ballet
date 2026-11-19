"""Configuration de Ballet : défauts du plugin, surcharges du projet, vérifications.

    python3 ballet_config.py check [dossier-du-projet]   # liste les problèmes
    python3 ballet_config.py show  [dossier-du-projet]   # affiche la config fusionnée
"""

import json
import re
import sys
import tomllib
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
PROJECT_CONFIG = Path(".ballet") / "config.toml"
PERIMETER_KEYS = ("writes", "except", "extra_writes", "extra_except", "branches")

ROLES = ("dramaturg", "choreographer", "dancer", "critic")
CLIS = ("claude", "grok", "mistral-vibe", "codex", "opencode", "gemini-cli", "kimi")
MUTATION_REPORT_FORMATS = ("cargo-mutants",)


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
        + _rehearsal_problems(config)
        + _threshold_problems(config)
        + _mutation_problems(config)
        + _policy_problems(config)
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
        raise ConfigError(f"{path}: invalid TOML ({error})") from error


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
        return ["[project] specs missing: run /ballet:init-project"]
    problems = []
    if not isinstance(project["specs"], str):
        problems.append("[project] specs must be a string")
    if not isinstance(project.get("adr"), str) or not project.get("adr"):
        problems.append("[project] adr must be a folder path, e.g. docs/ADR/")
    if not _is_language_code(project.get("specs_language")):
        problems.append("[project] specs_language must be a language code, e.g. en or fr")
    return problems


def _repo_problems(config):
    repos = _table(config, "repos")
    if not repos:
        return ["no repo declared: add a [repos.<name>] section (or run /ballet:init-project)"]
    problems = []
    for name, repo in repos.items():
        problems += _single_repo_problems(name, repo, known=repos)
    return problems + _needs_cycle_problems(repos)


def _single_repo_problems(name, repo, known):
    if not isinstance(repo, dict):
        return [f"[repos.{name}] must be a table"]
    problems = []
    for field in ("path", "proof"):
        if not repo.get(field):
            problems.append(f"[repos.{name}] {field} missing")
    for needed in repo.get("needs", []):
        if needed not in known:
            problems.append(f"[repos.{name}] needs: unknown repo '{needed}'")
    return problems + _mutation_tool_problems(name, repo.get("mutation", []))


def _mutation_tool_problems(repo_name, tools):
    """Une entrée `[[repos.<repo>.mutation]]` par outil : de quoi le lancer et lire son rapport."""
    where = f"[[repos.{repo_name}.mutation]]"
    if not isinstance(tools, list) or not all(isinstance(tool, dict) for tool in tools):
        return [f"{where} must be an array of tables"]
    problems = []
    for tool in tools:
        problems += _single_mutation_tool_problems(f"{where} {tool.get('name', '?')}", tool)
    names = [tool.get("name") for tool in tools]
    if len(set(names)) != len(names):
        problems.append(f"{where}: each tool needs its own name")
    return problems


def _single_mutation_tool_problems(where, tool):
    problems = [f"{where}: {key} must be a non-empty string" for key in ("name", "command", "config")
                if not isinstance(tool.get(key), str) or not tool.get(key)]
    report = tool.get("report")
    if not isinstance(report, dict) or not isinstance(report.get("path"), str) or not report.get("path"):
        problems.append(f"{where}: report must be {{ path = \"...\", format = \"...\" }}")
    elif report.get("format") not in MUTATION_REPORT_FORMATS:
        problems.append(f"{where}: report format must be one of {', '.join(MUTATION_REPORT_FORMATS)}")
    if not _is_glob_list(tool.get("paths", [])):
        problems.append(f"{where}: paths must be a list of globs")
    return problems


def _needs_cycle_problems(repos):
    needs = {
        name: [n for n in repo.get("needs", []) if n in repos]
        for name, repo in repos.items()
        if isinstance(repo, dict)
    }
    cycle = _find_cycle(needs)
    return [f"cycle in needs: {' → '.join(cycle)}"] if cycle else []


def _rule_problems(config, plugin_root):
    known = {path.parent.name for path in (plugin_root / "skills").glob("*/SKILL.md")}
    rules = _table(config, "project").get("rules", [])
    return [f"[project] rules: unknown rule '{rule}'" for rule in rules if rule not in known]


def _role_problems(config):
    roles = _table(config, "roles")
    problems = [f"[roles.{name}]: unknown role" for name in roles if name not in ROLES]
    for role in ROLES:
        settings = roles.get(role)
        if not isinstance(settings, dict) or not settings.get("cli"):
            problems.append(f"[roles.{role}] cli missing")
        elif settings["cli"] not in CLIS:
            problems.append(f"[roles.{role}] unknown cli '{settings['cli']}'")
    return problems


def _critic_dancer_problems(config):
    """Critic ≠ Dancer : CLI différents, ou même CLI avec deux modèles explicites différents."""
    roles = _table(config, "roles")
    dancer, critic = roles.get("dancer"), roles.get("critic")
    if not isinstance(dancer, dict) or not isinstance(critic, dict):
        return []
    if dancer.get("cli") != critic.get("cli") or _models_differ(dancer, critic):
        return []
    return ["Critic ≠ Dancer: same CLI without two different explicit models"]


def _rehearsal_problems(config):
    if not isinstance(_table(config, "rehearsal").get("plan_approval"), bool):
        return ["[rehearsal] plan_approval must be true or false"]
    return []


def _threshold_problems(config):
    escalation = _table(config, "escalation")
    problems = []
    for key in ("max_round_trips", "max_exchange_rounds", "max_diff_lines", "ci_wait_seconds",
                "proof_timeout_seconds"):
        value = escalation.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            problems.append(f"[escalation] {key} must be a positive integer")
    if not isinstance(escalation.get("max_diff_strict"), bool):
        problems.append("[escalation] max_diff_strict must be true or false")
    if not _is_glob_list(escalation.get("diff_exclude")):
        problems.append("[escalation] diff_exclude must be a list of globs")
    return problems


def _mutation_problems(config):
    mutation = _table(config, "mutation")
    problems = [] if isinstance(mutation.get("enabled"), bool) else ["[mutation] enabled must be true or false"]
    timeout = mutation.get("timeout_seconds")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1:
        problems.append("[mutation] timeout_seconds must be a positive integer")
    return problems


def _policy_problems(config):
    """Les données de la politique ; `.ballet/*` reste interdit, sinon un rôle pourrait réécrire la politique elle-même."""
    policy = _table(config, "policy")
    problems = [f"[policy] {key} must be a list of globs"
                for key in ("sensitive_zones", "forbidden_zones") if not _is_glob_list(policy.get(key, []))]
    problems += _perimeter_problems(_table(policy, "roles"))
    for language, settings in _table(policy, "test_names").items():
        problems += _test_names_problems(language, settings)
    return problems or _profile_protection_problems(config)


def _perimeter_problems(roles):
    problems = [f"[policy.roles.{name}]: unknown role" for name in roles if name not in ROLES]
    for role in ROLES:
        settings = roles.get(role)
        if not isinstance(settings, dict):
            problems.append(f"[policy.roles.{role}] missing")
            continue
        problems += [f"[policy.roles.{role}] {key} must be a list of globs"
                     for key in PERIMETER_KEYS if not _is_glob_list(settings.get(key, []))]
    return problems


def _profile_protection_problems(config):
    """Aucun rôle ne peut écrire le profil : il porte la politique elle-même."""
    import ballet_policy  # ici : ballet_policy lit sa config par ce module
    roles = ballet_policy.roles_writing_the_profile(ballet_policy.policy_of(config))
    return [f"[policy.roles.{role}] lets the {role} write {ballet_policy.PROFILE}: the profile holds the policy" for role in roles]


def _test_names_problems(language, settings):
    where = f"[policy.test_names.{language}]"
    if not isinstance(settings, dict) or not _is_glob_list(settings.get("extensions")) or not settings.get("extensions"):
        return [f"{where} extensions must be a non-empty list, e.g. [\".go\"]"]
    try:
        if re.compile(settings.get("pattern", "")).groups < 1:
            return [f"{where} pattern needs a group: its last one is the test name"]
    except (re.error, TypeError) as error:
        return [f"{where} pattern is not a valid regular expression ({error})"]
    return []


def _is_glob_list(value):
    return isinstance(value, list) and all(isinstance(glob, str) for glob in value)


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
    print("✓ valid configuration")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
