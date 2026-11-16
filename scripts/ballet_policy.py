"""La politique : ce qu'un rôle a fait du repo pendant son passage, vérifié sans jugement de modèle (PRD §5.3).

    python3 ballet_policy.py <home> <worktree>     # audite la branche du worktree comme un passage du Dancer

Le Conductor (`ballet_rehearsal.py`) l'appelle après chaque rôle et applique le résultat tel quel.

Pour tous : rester sur la branche de Rehearsal, ne pas réécrire l'historique (le `HEAD` d'avant reste un ancêtre),
ne créer ni supprimer de branche ni de tag (sauf `spike/*` pour le Choreographer), laisser l'arbre de travail propre
(sauf le Choreographer qui répond au Dancer : l'arbre du Dancer est alors en cours).
- Critic : `HEAD` n'a pas bougé.
- Choreographer : ses commits ne touchent que le dossier des ADR et `AGENTS.md`.
- Dancer : la branche, face à `main`, ne change ni l'espace specs, ni les ADR, ni `AGENTS.md` (sauf par les commits
  du Choreographer), ni une zone interdite ; aucun test présent sur `main` n'a disparu ni changé de nom.

Une zone est un glob `fnmatch` : `*` traverse aussi les `/`. Un glob sans `/` vaut à toute profondeur (`CLAUDE.md`),
un glob avec `/` part de la racine du repo (`.github/*`).

Un test est reconnu par son nom, selon le langage : `it("…")` ou `test("…")` (JS, TS), `#[test] fn …` (Rust),
`def test_…` (Python), `Scenario: …` (Gherkin). Le corps d'un test existant modifié reste à la charge du Critic.
"""

import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import PurePosixPath

import ballet_config

BASE = "origin/main"
ROLES = ("dancer", "choreographer", "critic")

# Le harnais, la CI et les hooks git : interdits à tous les rôles, quel que soit le projet.
HARNESS_ZONES = (
    "AGENTS.md", "CLAUDE.md", ".ballet/*", ".claude/*", ".agents/*", ".vibe/*", ".codex/*", ".grok/*", ".mcp.json",
    ".github/*", ".gitlab-ci.yml", ".circleci/*", ".husky/*", ".githooks/*", "lefthook.yml", ".pre-commit-config.yaml",
)
CHOREOGRAPHER_FILES = ("AGENTS.md",)

TEST_NAMES = {
    (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"): re.compile(r"\b(?:it|test)(?:\.\w+)?\(\s*(['\"`])(.+?)\1"),
    (".rs",): re.compile(r"#\[(?:[\w:]+::)?test\b[^\]]*\]\s*(?:#\[[^\]]*\]\s*)*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)"),
    (".py",): re.compile(r"^\s*(?:async\s+)?def\s+(test\w*)", re.MULTILINE),
    (".feature",): re.compile(r"^\s*(?:Scenario|Scenario Outline|Scenario Template|Example):\s*(.+?)\s*$", re.MULTILINE),
}


@dataclass
class Zones:
    """Les chemins protégés d'un projet : espace specs, ADR et zones sensibles du profil, en plus du harnais."""
    specs: str
    adr: str
    sensitive: list = field(default_factory=list)


@dataclass
class Passage:
    """Le passage d'un rôle dans le worktree : ce qu'il a reçu, et ce qu'on attend qu'il ait laissé."""
    role: str
    branch: str
    checkpoint: str = ""                          # `HEAD` quand le rôle a reçu la main
    refs: list = field(default_factory=list)      # branches et tags à ce moment
    owned: list = field(default_factory=list)     # les commits du Choreographer sur la branche
    answering: bool = False                       # le Choreographer répond pendant que le Dancer attend


def zones_of(config):
    project = config.get("project", {})
    return Zones(specs=project.get("specs", ""), adr=project.get("adr", ""),
                 sensitive=list(config.get("policy", {}).get("sensitive_zones", [])))


def violations(passage, zones, git):
    """La liste des violations du passage, vide s'il est en règle."""
    found = _stayed_on_branch(passage, git) + _kept_history(passage, git) + _kept_refs(passage, git)
    if not passage.answering:
        found += _clean_tree(git)
    if passage.role == "critic":
        found += _head_unmoved(passage, git)
    if passage.role == "choreographer":
        found += _choreographer_files(passage, zones, git)
    if passage.role == "dancer":
        found += _dancer_files(passage, zones, git) + _kept_tests(git)
    return found


def head(git):
    return git(["rev-parse", "HEAD"]).strip()


def refs(git):
    """Les branches et les tags locaux, partagés par tous les worktrees du repo."""
    return sorted(git(["for-each-ref", "--format=%(refname)", "refs/heads", "refs/tags"]).split())


def commits_since(checkpoint, git):
    return git(["rev-list", f"{checkpoint}..HEAD"]).split() if checkpoint else []


def main(argv):
    if len(argv) != 3:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    git = _git(argv[2])
    passage = Passage("dancer", git(["rev-parse", "--abbrev-ref", "HEAD"]).strip())
    found = violations(passage, zones_of(ballet_config.effective_config(argv[1])), git)
    print("\n".join(f"- {violation}" for violation in found) or "no violation")
    return 1 if found else 0


# --- pour tous les rôles ------------------------------------------------------


def _stayed_on_branch(passage, git):
    current = git(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    return [] if current == passage.branch else [f"the worktree is on `{current}`, not on `{passage.branch}`"]


def _kept_history(passage, git):
    """L'ancien `HEAD` reste un ancêtre du nouveau : aucun commit d'avant n'a disparu."""
    if not passage.checkpoint:
        return []
    lost = int(git(["rev-list", "--count", f"HEAD..{passage.checkpoint}"]).strip() or 0)
    return [f"history rewritten: {lost} commit(s) before {passage.checkpoint[:7]} no longer on the branch"] if lost else []


def _kept_refs(passage, git):
    if not passage.refs:
        return []
    before, after = set(passage.refs), set(refs(git))
    created = {ref for ref in after - before if not _allowed_ref(passage.role, ref)}
    return ([f"branch or tag created: {ref}" for ref in sorted(created)]
            + [f"branch or tag deleted: {ref}" for ref in sorted(before - after)])


def _allowed_ref(role, ref):
    return role == "choreographer" and ref.startswith("refs/heads/spike/")


def _clean_tree(git):
    dirty = git(["status", "--porcelain"]).splitlines()
    return [f"uncommitted changes left in the worktree: {', '.join(line[3:] for line in dirty[:5])}"] if dirty else []


# --- par rôle -----------------------------------------------------------------


def _head_unmoved(passage, git):
    return [] if head(git) == passage.checkpoint else [f"HEAD moved from {passage.checkpoint[:7]}: the Critic is read-only"]


def _choreographer_files(passage, zones, git):
    changed = git(["diff", "--name-only", f"{passage.checkpoint}..HEAD"]).split() if passage.checkpoint else []
    return [f"{path}: the Choreographer writes only ADRs and AGENTS.md"
            for path in changed if not _is_choreographer_file(path, zones)]


def _dancer_files(passage, zones, git):
    """Ce que la branche change face à `main`, au net : un changement annulé par un commit suivant n'en est plus un."""
    base = _base(git)
    found = []
    for path in git(["diff", "--name-only", "--no-renames", f"{base}..HEAD"]).split():
        zone = _forbidden_zone(path, zones)
        if zone and not (_is_choreographer_file(path, zones) and _only_choreographer_commits(path, base, passage.owned, git)):
            found.append(f"{path}: {zone}")
    return found


def _kept_tests(git):
    """Chaque test présent sur `main` existe encore sous le même nom."""
    base = _base(git)
    found = []
    for status, path in _modified_or_deleted(base, git):
        before = _test_names(path, git(["show", f"{base}:{path}"]))
        after = _test_names(path, git(["show", f"HEAD:{path}"]) if status == "M" else "")
        found += [f"{path}: existing test removed or renamed: {name}" for name in sorted((before - after).elements())]
    return found


# --- détails ------------------------------------------------------------------


def _forbidden_zone(path, zones):
    """La zone qui interdit ce chemin au Dancer, en clair ; `None` s'il est libre."""
    if _in_folder(path, zones.specs):
        return "the specs space"
    if _in_folder(path, zones.adr):
        return "the ADR folder"
    if any(_matches(path, glob) for glob in HARNESS_ZONES):
        return "the harness, the CI or the git hooks"
    if any(_matches(path, glob) for glob in zones.sensitive):
        return "a sensitive zone of [policy] sensitive_zones"
    return None


def _is_choreographer_file(path, zones):
    return _in_folder(path, zones.adr) or path in CHOREOGRAPHER_FILES


def _only_choreographer_commits(path, base, owned, git):
    authors = git(["log", "--format=%H", f"{base}..HEAD", "--", path]).split()
    return bool(authors) and set(authors) <= set(owned)


def _matches(path, glob):
    if "/" in glob:
        return fnmatch(path, glob)
    return fnmatch(PurePosixPath(path).name, glob)


def _in_folder(path, folder):
    folder = folder.strip("/")
    return bool(folder) and (path == folder or path.startswith(folder + "/"))


def _base(git):
    return git(["merge-base", BASE, "HEAD"]).strip()


def _modified_or_deleted(base, git):
    for line in git(["diff", "--name-status", "--no-renames", f"{base}..HEAD"]).splitlines():
        status, path = line.split("\t", 1)
        if status in ("M", "D"):
            yield status, path


def _test_names(path, text):
    for extensions, pattern in TEST_NAMES.items():
        if path.endswith(extensions):
            return Counter(match.groups()[-1] for match in pattern.finditer(text))
    return Counter()


def _git(repo):
    def run(arguments):
        return subprocess.run(["git", "-C", repo, *arguments], capture_output=True, text=True, check=True).stdout
    return run


if __name__ == "__main__":
    sys.exit(main(sys.argv))
