"""Le test de mutation d'une branche : Ballet porte la méthode, le projet l'outil.

    python3 ballet_mutation.py run [--force]   # depuis le home du projet : la branche du repo face à origin/main

C'est le chemin de la Rehearsal (le nœud après la preuve), lancé à la main par un dev. Chaque outil est une entrée
`[[repos.<repo>.mutation]]` du profil (`name`, `command`, `config`, `report = { path, format }`, `paths` facultatif).
Pour chacun :

- le diff de la branche contre son ancêtre commun avec `origin/main`, filtré par `paths` (fnmatch sur le chemin
  entier, `*` traverse les `/`) ; un outil sans changement est sauté ;
- le périmètre passé à la commande par placeholders : `{diff}` (un fichier), `{files}`, `{ranges}` (`fichier:début-fin`,
  les lignes ajoutées ou modifiées) ;
- l'ancien rapport supprimé, la commande lancée dans le repo ; **son code de sortie décide**, rien d'autre ;
- son rapport lu et normalisé (tués, survivants, invalides, score) quand il est lisible : absent ou illisible, on le
  dit, sans jamais bloquer.

Les outils passent l'un après l'autre, même après un rouge, dans un budget commun (`[mutation] timeout_seconds`).
`[mutation] enabled = false` coupe la mutation ; `--force` la lance quand même. Le log entier, le diff, le rapport
natif copié et le détail normalisé vont dans `.ballet/run/manual/` (dans `.ballet/run/<ID>/` pour une Rehearsal).
Sort avec 1 si un outil est rouge, 2 sur un usage invalide.
"""

import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from fnmatch import fnmatch
from pathlib import Path

import ballet_config

BASE = "origin/main"
SURVIVORS_IN_EVENT = 50   # les survivants au journal ; la liste entière est dans le détail
OUTPUT_LINES = 60         # la fin de la sortie, quand le rapport ne dit rien des survivants
MANUAL_DIR = Path(".ballet") / "run" / "manual"


@dataclass
class Tool:
    """Un outil de mutation du profil."""
    name: str
    command: str
    config: str
    report_path: str
    report_format: str
    paths: list = field(default_factory=list)


@dataclass
class Scope:
    """Ce que la branche change, pour un outil : le diff filtré, ses fichiers et ses plages de lignes."""
    diff: str
    files: list
    ranges: list


@dataclass
class Outcome:
    """Ce qu'a donné un outil : vert ou non (son code de sortie), et son rapport normalisé, ou pourquoi il manque."""
    tool: str
    passed: bool
    timed_out: bool
    exit_code: object
    seconds: int
    head: str
    log: str
    details: str
    report: object            # le rapport normalisé (dict), ou "missing", ou "unreadable: …"

    def lists_survivors(self):
        return isinstance(self.report, dict) and bool(self.report["survivors"])

    def report_status(self):
        """`read` pour un rapport lu ; sinon sa raison (`missing`, `unreadable: …`)."""
        return "read" if isinstance(self.report, dict) else self.report

    def survivors_text(self):
        """Les survivants, un par ligne ; sans eux, la fin de la sortie."""
        if self.lists_survivors():
            return "\n".join(survivor["mutant"] for survivor in self.report["survivors"])
        return "\n".join(_log_lines(self.log)[-OUTPUT_LINES:])

    def event(self):
        """Le détail de `mutation-end` : les survivants plafonnés, la liste entière restant dans `details`."""
        detail = asdict(self)
        if isinstance(self.report, dict):
            survivors = self.report["survivors"]
            detail["report"] = {**self.report, "survivors": survivors[:SURVIVORS_IN_EVENT], "survivors_total": len(survivors)}
        return detail


def tools_of(repo):
    """Les outils déclarés pour un repo du profil, dans l'ordre."""
    return [Tool(entry["name"], entry["command"], entry["config"], entry["report"]["path"], entry["report"]["format"],
                 entry.get("paths", [])) for entry in repo.get("mutation", [])]


def scopes_of(tools, git):
    """Les outils que la branche touche, chacun avec son périmètre ; les autres sont sautés."""
    diff = _branch_diff(git)
    scoped = [(tool, scope_of(diff, tool.paths)) for tool in tools]
    return [(tool, scope) for tool, scope in scoped if scope.files]


def scope_of(diff, paths):
    """Le diff réduit aux fichiers que `paths` retient (tous sans `paths`), ses fichiers et ses plages."""
    sections = [(path, text) for path, text in _file_sections(diff) if not paths or any(fnmatch(path, glob) for glob in paths)]
    kept = "".join(text for _, text in sections)
    return Scope(kept, _changed_files(kept), ranges_of(kept))


def run_tools(scoped, worktree, folder, prefix, budget, git, journal, run_command=None):
    """Les outils l'un après l'autre, même après un rouge, dans un budget commun ; chacun journalisé à son début
    (`mutation-start`) et à sa fin (`mutation-end`)."""
    deadline, folder = time.monotonic() + budget, Path(folder).resolve()
    outcomes = []
    for tool, scope in scoped:
        label, head = f"{prefix}-{tool.name}", _head(git)
        journal("mutation-start", {"tool": tool.name, "command": expand(tool.command, folder / f"{label}.diff", scope),
                                   "head": head, "files": len(scope.files), "ranges": len(scope.ranges)})
        outcome = mutate(tool, scope, worktree, folder, label, deadline - time.monotonic(), head,
                         run_command or run_command_with_timeout)
        journal("mutation-end", outcome.event())
        outcomes.append(outcome)
    return outcomes


def mutate(tool, scope, worktree, folder, label, timeout, head, run_command):
    """Un outil : l'ancien rapport supprimé, la commande lancée sur son périmètre, son rapport lu et gardé."""
    folder.mkdir(parents=True, exist_ok=True)
    diff_path, log_path, details_path = folder / f"{label}.diff", folder / f"{label}.log", folder / f"{label}.json"
    report_path = Path(worktree) / tool.report_path
    _remove(report_path)
    diff_path.write_text(scope.diff, encoding="utf-8")
    started = time.monotonic()
    exit_code, timed_out = run_command(expand(tool.command, diff_path, scope), worktree, timeout, log_path)
    seconds = round(time.monotonic() - started)
    report = read_report(report_path, tool.report_format)
    _keep_native_report(report_path, folder / f"{label}-report{report_path.suffix}")
    outcome = Outcome(tool.name, exit_code == 0 and not timed_out, timed_out, exit_code, seconds, head,
                      str(log_path), str(details_path), report)
    details_path.write_text(json.dumps(asdict(outcome), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return outcome


def expand(command, diff_path, scope):
    """Les placeholders du profil : `{diff}` (le fichier du diff), `{files}`, `{ranges}`, quotés pour le shell."""
    return (command.replace("{diff}", shlex.quote(str(diff_path)))
            .replace("{files}", " ".join(shlex.quote(path) for path in scope.files))
            .replace("{ranges}", " ".join(shlex.quote(line_range) for line_range in scope.ranges)))


def ranges_of(diff):
    """Les lignes ajoutées ou modifiées, côté branche, en plages `fichier:début-fin`."""
    ranges = []
    for path, text in _file_sections(diff):
        if not _deleted(text):
            ranges += [f"{path}:{start}-{end}" for start, end in _consecutive(_added_lines(text))]
    return ranges


def read_report(path, report_format):
    """Le rapport normalisé, ou la raison de son absence : la lecture ne bloque jamais."""
    if not Path(path).is_file():
        return "missing"
    try:
        return READERS[report_format](json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        return f"unreadable: {type(error).__name__}: {error}"


def run_command_with_timeout(command, cwd, timeout, log_path):
    """Une ligne de shell, sa sortie dans le log ; trop longue, son groupe de processus est tué."""
    if timeout <= 0:
        Path(log_path).write_text("Not started: the mutation budget was spent by the tools before it.\n", encoding="utf-8")
        return None, True
    with open(log_path, "w", encoding="utf-8") as log:
        process = subprocess.Popen(command, shell=True, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return process.wait(timeout=timeout), False
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            return None, True


def main(argv, home="."):
    """`run` : la mutation de la branche du repo, comme dans une Rehearsal, ses résultats affichés."""
    if argv[1:] not in (["run"], ["run", "--force"]):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    config = ballet_config.effective_config(home)
    problems = ballet_config.find_problems(config)
    if problems:
        print("The profile is not valid: " + "; ".join(problems), file=sys.stderr)
        return 2
    return _run_by_hand(config, home, force="--force" in argv)


# --- le run d'un dev ----------------------------------------------------------


def _run_by_hand(config, home, force):
    if not config["mutation"]["enabled"] and not force:
        print("Mutation skipped: disabled in the profile ([mutation] enabled = false); --force runs it anyway.")
        return 0
    repo = next(iter(config["repos"].values()))
    worktree = str((Path(home) / repo["path"]).resolve())
    git = _git(worktree)
    scoped = scopes_of(tools_of(repo), git)
    if not scoped:
        print("Mutation skipped: " + ("the diff touches no mutation tool." if repo.get("mutation") else "no mutation tool in the profile."))
        return 0
    outcomes = run_tools(scoped, worktree, Path(home) / MANUAL_DIR, "mutation", config["mutation"]["timeout_seconds"],
                         git, _print_event)
    return 0 if all(outcome.passed for outcome in outcomes) else 1


def _print_event(event, detail):
    if event == "mutation-start":
        print(f"{detail['tool']}: {detail['command']}  ({detail['files']} files, {detail['ranges']} ranges)", flush=True)
        return
    status = "timed out" if detail["timed_out"] else "green" if detail["passed"] else f"red (exit {detail['exit_code']})"
    print(f"{detail['tool']}: {status} in {detail['seconds']}s; {_report_line(detail['report'])}; log {detail['log']}")
    if isinstance(detail["report"], dict):
        for survivor in detail["report"]["survivors"]:
            print(f"  survived: {survivor['mutant']}")


def _report_line(report):
    if not isinstance(report, dict):
        return f"report {report}"
    return (f"{report['killed']} killed, {report['survived']} survived, {report['invalid']} invalid, "
            f"score {report['score'] if report['score'] is not None else 'n/a'}")


# --- le diff ------------------------------------------------------------------


def _branch_diff(git):
    base = git(["merge-base", BASE, "HEAD"]).strip()
    return git(["diff", "--no-color", "--no-ext-diff", base, "HEAD"])


def _file_sections(diff):
    """Le diff coupé par fichier : (chemin côté branche, ou d'origine pour un fichier supprimé ; texte de la section)."""
    sections, current = [], []
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git ") and current:
            sections.append(current)
            current = []
        current.append(line)
    if current:
        sections.append(current)
    return [(_section_path(lines), "".join(lines)) for lines in sections]


def _section_path(lines):
    new = next((line[6:].rstrip("\n") for line in lines if line.startswith("+++ b/")), None)
    old = next((line[6:].rstrip("\n") for line in lines if line.startswith("--- a/")), None)
    return new or old or lines[0].rstrip("\n").split(" b/", 1)[-1]


def _changed_files(diff):
    return [path for path, text in _file_sections(diff) if not _deleted(text)]


def _deleted(section):
    return "\n+++ /dev/null" in section


def _added_lines(section):
    """Les numéros, côté branche, des lignes `+` de chaque hunk."""
    added, line_number = [], None
    for line in section.splitlines():
        if line.startswith("@@"):
            line_number = int(line.split("+", 1)[1].split(" ", 1)[0].split(",")[0])
        elif line_number is None or line.startswith("\\"):
            continue
        elif line.startswith("+"):
            added.append(line_number)
            line_number += 1
        elif not line.startswith("-"):
            line_number += 1
    return added


def _consecutive(numbers):
    groups = []
    for number in numbers:
        if groups and number == groups[-1][1] + 1:
            groups[-1][1] = number
        else:
            groups.append([number, number])
    return [tuple(group) for group in groups]


# --- les rapports -------------------------------------------------------------


def _cargo_mutants(report):
    """`mutants.out/outcomes.json` de cargo-mutants : les totaux en tête, un `MissedMutant` par survivant."""
    survivors = [_cargo_mutant(outcome["scenario"]["Mutant"]) for outcome in report["outcomes"]
                 if outcome["summary"] == "MissedMutant"]
    return _normalized(killed=report["caught"], survived=report["missed"], invalid=report["unviable"],
                       timeouts=report["timeout"], survivors=survivors)


def _cargo_mutant(mutant):
    return {"file": mutant["file"], "line": mutant["span"]["start"]["line"], "mutant": mutant["name"]}


def _normalized(killed, survived, invalid, timeouts, survivors):
    tested = killed + survived
    return {"killed": killed, "survived": survived, "invalid": invalid, "timeouts": timeouts,
            "score": round(killed / tested, 3) if tested else None, "survivors": survivors}


READERS = {"cargo-mutants": _cargo_mutants}


# --- outils -------------------------------------------------------------------


def _log_lines(path):
    if not Path(path).is_file():
        return []
    return Path(path).read_text(encoding="utf-8", errors="replace").rstrip().splitlines()


def _remove(path):
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _keep_native_report(report_path, copy):
    if report_path.is_file():
        shutil.copyfile(report_path, copy)


def _head(git):
    return git(["rev-parse", "HEAD"]).strip()


def _git(repo):
    def run(arguments):
        return subprocess.run(["git", "-C", repo, *arguments], capture_output=True, text=True, check=True).stdout
    return run


if __name__ == "__main__":
    sys.exit(main(sys.argv))
