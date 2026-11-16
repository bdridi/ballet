"""La taille d'une Rehearsal : les lignes changées (ajoutées et supprimées) de sa branche face à `origin/main`,
hors des fichiers exclus.

    python3 ballet_size.py <repo> <rehearsal/ID> [--exclude "*.lock,pnpm-lock.yaml"]

Un motif d'exclusion suit `fnmatch` sur le chemin entier : `*` traverse aussi les `/`
(`*.lock` exclut `Cargo.lock` comme `apps/web/yarn.lock`). Un fichier binaire compte pour 0.
"""

import subprocess
import sys
from dataclasses import dataclass, field
from fnmatch import fnmatch

BASE = "origin/main"


@dataclass
class Size:
    counted: int = 0
    excluded: int = 0
    excluded_files: list = field(default_factory=list)

    def over(self, limit):
        return self.counted > limit


def branch_size(branch, exclude, git):
    """Mesure la branche face à `origin/main`, depuis leur ancêtre commun."""
    return measure(git(["diff", "--numstat", f"{BASE}...{branch}"]), exclude)


def measure(numstat, exclude):
    size = Size()
    for path, lines in _changed_files(numstat):
        if _is_excluded(path, exclude):
            size.excluded += lines
            size.excluded_files.append(path)
        else:
            size.counted += lines
    return size


def main(argv):
    if len(argv) not in (3, 5) or argv[3:4] not in ([], ["--exclude"]):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    exclude = [glob for glob in argv[4].split(",") if glob] if len(argv) == 5 else []
    size = branch_size(argv[2], exclude, _git(argv[1]))
    print(f"{size.counted} lines counted, {size.excluded} excluded ({', '.join(size.excluded_files) or 'no file'})")
    return 0


# --- détails ----------------------------------------------------------------


def _changed_files(numstat):
    """`ajoutées<TAB>supprimées<TAB>chemin` par fichier ; un binaire a `-` pour les deux."""
    for line in numstat.splitlines():
        added, deleted, path = line.split("\t", 2)
        yield path, _count(added) + _count(deleted)


def _count(value):
    return 0 if value == "-" else int(value)


def _is_excluded(path, exclude):
    return any(fnmatch(path, glob) for glob in exclude)


def _git(repo):
    def run(arguments):
        return subprocess.run(["git", "-C", repo, *arguments], capture_output=True, text=True, check=True).stdout
    return run


if __name__ == "__main__":
    sys.exit(main(sys.argv))
