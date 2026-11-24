"""La politique : ce qu'un rôle a fait du repo pendant son passage, vérifié sans jugement de modèle (PRD §5.3).

    python3 ballet_policy.py <home> <worktree>     # audite la branche du worktree comme un passage du Dancer

Le Conductor (`ballet_rehearsal.py`) l'appelle après chaque rôle et applique le résultat tel quel.

Le périmètre d'un rôle vient de `[policy.roles.<rôle>]` : un chemin est permis s'il est dans `writes` ou
`extra_writes`, et hors de `except` et `extra_except` (`except` l'emporte). Les défauts du plugin sont la méthode :
- Dramaturg : l'espace specs.
- Choreographer : le dossier des ADR et `AGENTS.md` ; il peut créer des branches `spike/*`, jamais mergées.
- Dancer : tout son repo, sauf l'espace specs, les ADR, les zones interdites et les zones sensibles.
- Critic : rien, `HEAD` ne bouge pas.

Pour tous : rester sur la branche de Rehearsal, ne pas réécrire l'historique (le `HEAD` d'avant reste un ancêtre),
ne créer ni supprimer de branche ni de tag, laisser l'arbre de travail propre (sauf un rôle qui répond au Dancer :
l'arbre du Dancer est alors en cours). Le Dancer est jugé sur le diff net de sa branche face au `HEAD` qu'il a reçu
(noté par le Conductor à sa première mission : les commits du Choreographer et du Dramaturg d'avant ne comptent pas ;
à défaut, le `HEAD` du worktree à son ouverture, puis l'ancêtre commun avec `origin/main`), hors des fichiers que
seuls les commits des autres rôles, venus pendant son travail, ont touchés.

Un test peut changer : un refacto ou une évolution rend une règle, donc un test, obsolète, et le Dancer le retire, le
renomme ou le réécrit sans rien déclarer. La politique ne le bloque pas ; elle en tient la liste (`removed_tests` : les
tests présents au départ qui n'ont plus leur nom dans la branche, avec leur fichier) pour la mission du Critic, qui
juge si le changement est légitime.

Les données viennent de la config (`[policy]` du plugin, surchargé par le projet) : `forbidden_zones`,
`sensitive_zones`, `roles` (le périmètre de la méthode, remplaçable, et l'extension du projet) et, par langage, `test_names` (extensions et motif du nom,
qui servent à reconnaître un test pour la liste du Critic).
Une zone est un glob `fnmatch` : `*` traverse aussi les `/`. Un glob sans `/` vaut à toute profondeur (`CLAUDE.md`),
un glob avec `/` part de la racine du repo (`.github/*`). `@specs`, `@adr`, `@forbidden` et `@sensitive` nomment
l'espace specs, le dossier des ADR, `forbidden_zones` et `sensitive_zones`. Le corps d'un test modifié reste au Critic.
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
ROLES = ("dramaturg", "choreographer", "dancer", "critic")
PROFILE = ".ballet/config.toml"


@dataclass
class Perimeter:
    writes: list = field(default_factory=list)
    excepted: list = field(default_factory=list)
    branches: list = field(default_factory=list)     # les branches qu'il peut créer

WHY = {
    "@specs": "the specs space",
    "@adr": "the ADR folder",
    "@forbidden": "a forbidden zone of [policy] forbidden_zones",
    "@sensitive": "a sensitive zone of [policy] sensitive_zones",
}


@dataclass
class Policy:
    """Les données de la politique : les périmètres (méthode et projet réunis), les lieux nommés, les tests."""
    perimeters: dict                                       # rôle → Perimeter
    places: dict                                           # `@specs`, `@adr`… → leurs globs
    test_names: list = field(default_factory=list)         # (extensions, motif compilé) par langage


@dataclass
class Passage:
    """Le passage d'un rôle dans le worktree : ce qu'il a reçu, et ce qu'on attend qu'il ait laissé."""
    role: str
    branch: str
    checkpoint: str = ""                          # `HEAD` quand le rôle a reçu la main
    refs: list = field(default_factory=list)      # branches et tags à ce moment
    owned: list = field(default_factory=list)     # les commits des autres rôles, vérifiés à leur passage
    answering: bool = False                       # le rôle répond pendant que le Dancer attend
    dancer_start: str = ""                        # `HEAD` quand le Dancer a reçu la branche : ce qu'il a fait en part
    base: str = ""                                # sans `dancer_start`, le point de départ de la branche ; vide, l'ancêtre commun avec `origin/main`


def policy_of(config):
    project, policy = config.get("project", {}), config.get("policy", {})
    places = {"@specs": _folder_globs(project.get("specs", "")), "@adr": _folder_globs(project.get("adr", "")),
              "@forbidden": list(policy.get("forbidden_zones", [])), "@sensitive": list(policy.get("sensitive_zones", []))}
    return Policy(perimeters={role: _perimeter(policy.get("roles", {}).get(role, {})) for role in ROLES},
                  places=places,
                  test_names=[(tuple(language["extensions"]), re.compile(language["pattern"]))
                              for language in policy.get("test_names", {}).values()])


def violations(passage, policy, git):
    """La liste des violations du passage, vide s'il est en règle."""
    found = _stayed_on_branch(passage, git) + _kept_history(passage, git) + _kept_refs(passage, policy, git)
    if not passage.answering:
        found += _clean_tree(git)
    if passage.role == "critic":
        found += _head_unmoved(passage, git)
    elif passage.role == "dancer":
        found += _branch_within_perimeter(passage, policy, git)
    else:
        found += _passage_within_perimeter(passage, policy, git)
    return found


def roles_writing_the_profile(policy):
    """Les rôles dont le périmètre couvre le profil : la config qui les permet est refusée."""
    return [role for role in ROLES if role != "critic" and not _refusal(PROFILE, role, policy)]


def head(git):
    return git(["rev-parse", "HEAD"]).strip()


def refs(git):
    """Les branches et les tags locaux, partagés par tous les worktrees du repo."""
    return sorted(git(["for-each-ref", "--format=%(refname)", "refs/heads", "refs/tags"]).split())


def dirty_files(git):
    """Les fichiers modifiés ou non suivis du worktree."""
    return [line[3:] for line in git(["status", "--porcelain"]).splitlines()]


def commits_since(checkpoint, git):
    return git(["rev-list", f"{checkpoint}..HEAD"]).split() if checkpoint else []


def removed_tests(passage, policy, git):
    """Les tests présents quand le Dancer a reçu la branche qui n'y ont plus leur nom, retirés ou renommés, un par ligne
    `fichier: nom` : la liste que le Critic juge (une évolution ou un refacto peut les rendre obsolètes)."""
    base = _base(passage, git)
    found = []
    for status, path in _modified_or_deleted(base, git):
        before = _test_names(path, policy, git(["show", f"{base}:{path}"]))
        after = _test_names(path, policy, git(["show", f"HEAD:{path}"]) if status == "M" else "")
        found += [f"{path}: {name}" for name in sorted((before - after).elements())]
    return found


def main(argv):
    if len(argv) != 3:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    git = _git(argv[2])
    passage = Passage("dancer", git(["rev-parse", "--abbrev-ref", "HEAD"]).strip())
    found = violations(passage, policy_of(ballet_config.effective_config(argv[1])), git)
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


def _kept_refs(passage, policy, git):
    if not passage.refs:
        return []
    before, after = set(passage.refs), set(refs(git))
    branches = policy.perimeters[passage.role].branches
    created = {ref for ref in after - before if not any(fnmatch(ref, f"refs/heads/{glob}") for glob in branches)}
    return ([f"branch or tag created: {ref}" for ref in sorted(created)]
            + [f"branch or tag deleted: {ref}" for ref in sorted(before - after)])


def _clean_tree(git):
    dirty = dirty_files(git)
    return [f"uncommitted changes left in the worktree: {', '.join(dirty[:5])}"] if dirty else []


# --- par rôle -----------------------------------------------------------------


def _head_unmoved(passage, git):
    return [] if head(git) == passage.checkpoint else [f"HEAD moved from {passage.checkpoint[:7]}: the Critic is read-only"]


def _passage_within_perimeter(passage, policy, git):
    """Le Dramaturg et le Choreographer : chaque fichier changé par leurs commits du passage."""
    changed = git(["diff", "--name-only", f"{passage.checkpoint}..HEAD"]).split() if passage.checkpoint else []
    return [f"{path}: {refusal}" for path in changed if (refusal := _refusal(path, passage.role, policy))]


def _branch_within_perimeter(passage, policy, git):
    """Le Dancer : ce que la branche change depuis qu'il l'a reçue, au net (un changement annulé n'en est plus un),
    hors des fichiers que seuls les commits des autres rôles, venus pendant son travail, ont touchés."""
    base = _base(passage, git)
    found = []
    for path in git(["diff", "--name-only", "--no-renames", f"{base}..HEAD"]).split():
        refusal = _refusal(path, "dancer", policy)
        if refusal and not _only_owned_commits(path, base, passage.owned, git):
            found.append(f"{path}: {refusal}")
    return found


# --- détails ------------------------------------------------------------------


def _perimeter(settings):
    """La méthode (`writes`, `except`) et ce que le projet y ajoute (`extra_writes`, `extra_except`)."""
    return Perimeter(writes=settings.get("writes", []) + settings.get("extra_writes", []),
                     excepted=settings.get("except", []) + settings.get("extra_except", []),
                     branches=settings.get("branches", []))


def _refusal(path, role, policy):
    """Pourquoi ce chemin est refusé au rôle, en clair ; `None` s'il est permis."""
    perimeter = policy.perimeters[role]
    for entry in perimeter.excepted:
        if _covers(path, entry, policy):
            return WHY.get(entry, f"excepted by [policy.roles.{role}]")
    if any(_covers(path, entry, policy) for entry in perimeter.writes):
        return None
    return f"outside the {role}'s perimeter ([policy.roles.{role}] writes, extra_writes)"


def _covers(path, entry, policy):
    return any(_matches(path, glob) for glob in policy.places.get(entry, [entry]))


def _only_owned_commits(path, base, owned, git):
    authors = git(["log", "--format=%H", f"{base}..HEAD", "--", path]).split()
    return bool(authors) and set(authors) <= set(owned)


def _matches(path, glob):
    if "/" in glob:
        return fnmatch(path, glob)
    return fnmatch(PurePosixPath(path).name, glob)


def _folder_globs(folder):
    folder = folder.strip("/")
    return [folder, f"{folder}/*"] if folder else []


def _base(passage, git):
    """Où le Dancer a reçu la branche ; sans ce `HEAD` (un ancien état), l'ouverture du worktree, puis `origin/main`."""
    return passage.dancer_start or passage.base or git(["merge-base", BASE, "HEAD"]).strip()


def _modified_or_deleted(base, git):
    for line in git(["diff", "--name-status", "--no-renames", f"{base}..HEAD"]).splitlines():
        status, path = line.split("\t", 1)
        if status in ("M", "D"):
            yield status, path


def _test_names(path, policy, text):
    for extensions, pattern in policy.test_names:
        if path.endswith(extensions):
            return Counter(match.groups()[-1] for match in pattern.finditer(text))
    return Counter()


def _git(repo):
    def run(arguments):
        return subprocess.run(["git", "-C", repo, *arguments], capture_output=True, text=True, check=True).stdout
    return run


if __name__ == "__main__":
    sys.exit(main(sys.argv))
