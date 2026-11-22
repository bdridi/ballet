import io
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_mutation  # noqa: E402
import ballet_store  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"

DIFF = """diff --git a/src/lib.rs b/src/lib.rs
index 1111111..2222222 100644
--- a/src/lib.rs
+++ b/src/lib.rs
@@ -1,4 +1,6 @@
 fn a() {}
-fn b() {}
+fn b() { 1 }
+fn c() {}
 fn d() {}
@@ -10,2 +12,3 @@ fn e() {}
 fn f() {}
+fn g() {}
 fn h() {}
diff --git a/apps/web/x.ts b/apps/web/x.ts
new file mode 100644
--- /dev/null
+++ b/apps/web/x.ts
@@ -0,0 +1,2 @@
+export const x = 1;
+export const y = 2;
diff --git a/src/old.rs b/src/old.rs
deleted file mode 100644
--- a/src/old.rs
+++ /dev/null
@@ -1 +0,0 @@
-fn gone() {}
"""


def tool(command="true", paths=None, report="mutants.out/outcomes.json"):
    return ballet_mutation.Tool("cargo-mutants", command, ".cargo/mutants.toml", report, "cargo-mutants", paths or [])


class ScopeTest(unittest.TestCase):
    def test_les_plages_sont_les_lignes_ajoutees_ou_modifiees_cote_branche(self):
        self.assertEqual(ballet_mutation.ranges_of(DIFF), ["src/lib.rs:2-3", "src/lib.rs:13-13", "apps/web/x.ts:1-2"])

    def test_sans_paths_le_perimetre_est_tout_le_diff_sans_les_fichiers_supprimes(self):
        scope = ballet_mutation.scope_of(DIFF, [])
        self.assertEqual(scope.files, ["src/lib.rs", "apps/web/x.ts"])
        self.assertEqual(scope.diff, DIFF)

    def test_paths_filtre_le_diff_ses_fichiers_et_ses_plages(self):
        scope = ballet_mutation.scope_of(DIFF, ["apps/*"])
        self.assertEqual((scope.files, scope.ranges), (["apps/web/x.ts"], ["apps/web/x.ts:1-2"]))
        self.assertTrue(scope.diff.startswith("diff --git a/apps/web/x.ts"))
        self.assertNotIn("src/lib.rs", scope.diff)

    def test_un_outil_que_le_diff_ne_touche_pas_est_saute(self):
        git = {("merge-base", "origin/main", "HEAD"): "base\n", ("diff", "--no-color", "--no-ext-diff", "base", "HEAD"): DIFF}
        scoped = ballet_mutation.scopes_of([tool(paths=["crates/*"]), tool(paths=["src/*"])], lambda arguments: git[tuple(arguments)])
        self.assertEqual([scope.files for _, scope in scoped], [["src/lib.rs"]])

    def test_depuis_la_derniere_mutation_verte_seul_ce_qui_a_change_compte(self):
        git = {("diff", "--no-color", "--no-ext-diff", "abc1234", "HEAD"): DIFF}
        scoped = ballet_mutation.scopes_of([tool(paths=["src/*"])], lambda arguments: git[tuple(arguments)], since="abc1234")
        self.assertEqual([scope.files for _, scope in scoped], [["src/lib.rs"]])

    def test_sans_paths_cargo_mutants_ne_retient_que_le_rust(self):
        entry = {"name": "rust", "command": "c", "config": "m.toml", "report": {"path": "o.json", "format": "cargo-mutants"}}
        declared = ballet_mutation.tools_of({"mutation": [entry]})[0]
        self.assertEqual(ballet_mutation.scope_of(DIFF, declared.paths).files, ["src/lib.rs"])

    def test_les_placeholders_passent_le_diff_les_fichiers_et_les_plages_quotes(self):
        scope = ballet_mutation.Scope("d", ["src/a b.rs", "src/c.rs"], ["src/a b.rs:1-2"])
        command = ballet_mutation.expand("mutate --in-diff {diff} --files {files} --mutate {ranges}", Path("/run/m 1.diff"), scope)
        self.assertEqual(command, "mutate --in-diff '/run/m 1.diff' --files 'src/a b.rs' src/c.rs --mutate 'src/a b.rs:1-2'")


class ReportTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)

    def test_le_rapport_de_cargo_mutants_27_est_normalise(self):
        report = ballet_mutation.read_report(FIXTURES / "cargo-mutants-27.1.0-outcomes.json", "cargo-mutants")
        self.assertEqual((report["killed"], report["survived"], report["invalid"], report["timeouts"], report["score"]),
                         (6, 7, 0, 0, 0.462))
        self.assertEqual(report["survivors"][0], {"file": "src/lib.rs", "line": 2, "mutant": "src/lib.rs:2:5: replace rank -> u8 with 1"})
        self.assertEqual(len(report["survivors"]), 7)

    def test_un_outil_qui_n_a_teste_aucun_mutant_viable_ne_prouve_rien(self):
        nothing = ballet_mutation._normalized(killed=0, survived=0, invalid=8, timeouts=0, survivors=[])
        outcome = ballet_mutation.Outcome("rust", True, False, 0, 50, "h", "l", "d", nothing)
        self.assertTrue(outcome.tested_nothing())
        self.assertFalse(ballet_mutation.Outcome("rust", True, False, 0, 50, "h", "l", "d", "missing").tested_nothing())

    def test_un_rapport_absent_ne_bloque_pas(self):
        self.assertEqual(ballet_mutation.read_report(self.folder / "none.json", "cargo-mutants"), "missing")

    def test_un_rapport_illisible_ne_bloque_pas_et_dit_pourquoi(self):
        (self.folder / "bad.json").write_text("{not json", encoding="utf-8")
        (self.folder / "odd.json").write_text('{"caught": 1}', encoding="utf-8")
        self.assertTrue(ballet_mutation.read_report(self.folder / "bad.json", "cargo-mutants").startswith("unreadable: JSONDecodeError"))
        self.assertEqual(ballet_mutation.read_report(self.folder / "odd.json", "cargo-mutants"), "unreadable: KeyError: 'outcomes'")

    def test_au_journal_les_survivants_sont_plafonnes_la_liste_entiere_reste_dans_le_detail(self):
        survivors = [{"file": "a.rs", "line": n, "mutant": f"a.rs:{n}"} for n in range(80)]
        report = ballet_mutation._normalized(killed=1, survived=80, invalid=0, timeouts=0, survivors=survivors)
        outcome = ballet_mutation.Outcome("t", False, False, 2, 1, "h", "log", "details", report)
        event = outcome.event()
        self.assertEqual((len(event["report"]["survivors"]), event["report"]["survivors_total"]), (50, 80))
        self.assertEqual(len(outcome.report["survivors"]), 80)

    def test_sans_survivants_lisibles_le_dancer_recoit_la_fin_de_la_sortie(self):
        log = self.folder / "m.log"
        log.write_text("\n".join(f"line {n}" for n in range(100)) + "\n", encoding="utf-8")
        outcome = ballet_mutation.Outcome("t", False, False, 2, 1, "h", str(log), "d", "missing")
        self.assertEqual(outcome.survivors_text().splitlines(), [f"line {n}" for n in range(40, 100)])


class RunToolsTest(unittest.TestCase):
    """Les outils lancés pour de vrai dans un shell, sur un faux périmètre."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.worktree = Path(self._tmp.name) / "wt"
        self.worktree.mkdir()
        self.folder = Path(self._tmp.name) / "run"
        self.events = []

    def run_tools(self, *tools, budget=30):
        scope = ballet_mutation.Scope(DIFF, ["src/lib.rs"], ["src/lib.rs:2-3"])
        return ballet_mutation.run_tools([(entry, scope) for entry in tools], str(self.worktree), self.folder, "mutation-1",
                                         budget, lambda arguments: "c0ffee1\n", lambda *event: self.events.append(event))

    def test_le_code_de_sortie_decide_et_les_outils_passent_tous_meme_apres_un_rouge(self):
        red = ballet_mutation.Tool("red", "echo boom; exit 2", "c", "r.json", "cargo-mutants")
        green = ballet_mutation.Tool("green", "echo fine", "c", "r.json", "cargo-mutants")
        outcomes = self.run_tools(red, green)
        self.assertEqual([(outcome.tool, outcome.passed, outcome.exit_code) for outcome in outcomes], [("red", False, 2), ("green", True, 0)])
        self.assertEqual([event for event, _ in self.events], ["mutation-start", "mutation-end", "mutation-start", "mutation-end"])
        self.assertEqual(Path(outcomes[0].log).read_text(), "boom\n")

    def test_la_commande_recoit_le_fichier_du_diff_et_tourne_dans_le_worktree(self):
        self.run_tools(tool("cp {diff} seen.diff; pwd > where"))
        self.assertEqual((self.worktree / "seen.diff").read_text(), DIFF)
        self.assertEqual(Path((self.worktree / "where").read_text().strip()).resolve(), self.worktree.resolve())
        self.assertIn(str(self.folder.resolve() / "mutation-1-cargo-mutants.diff"), self.events[0][1]["command"])

    def test_l_ancien_rapport_est_supprime_avant_le_run_et_le_nouveau_copie_a_cote_du_log(self):
        (self.worktree / "mutants.out").mkdir()
        (self.worktree / "mutants.out" / "outcomes.json").write_text("stale", encoding="utf-8")
        outcome = self.run_tools(tool("echo"))[0]
        self.assertEqual(outcome.report, "missing")
        native = (FIXTURES / "cargo-mutants-27.1.0-outcomes.json").read_text()
        (self.worktree / "fresh.json").write_text(native, encoding="utf-8")
        outcome = self.run_tools(tool("mkdir -p mutants.out; cp fresh.json mutants.out/outcomes.json; exit 2"))[0]
        self.assertEqual(outcome.report["survived"], 7)
        self.assertEqual((self.folder / "mutation-1-cargo-mutants-report.json").read_text(), native)
        self.assertEqual(json.loads(Path(outcome.details).read_text())["report"]["survived"], 7)

    def test_un_outil_vert_sans_mutant_dans_le_diff_n_a_pas_de_rapport_manquant(self):
        outcome = self.run_tools(tool("echo ' INFO No mutants to filter'"))[0]
        self.assertEqual((outcome.passed, outcome.report), (True, "no mutant in the diff"))

    def test_un_outil_rouge_sans_rapport_reste_un_rapport_manquant(self):
        outcome = self.run_tools(tool("echo 'No mutants to filter'; exit 2"))[0]
        self.assertEqual(outcome.report, "missing")

    def test_mutation_end_porte_statut_duree_head_et_rapport(self):
        self.run_tools(tool("exit 0"))
        end = self.events[1][1]
        self.assertEqual((end["tool"], end["passed"], end["timed_out"], end["head"], end["report"]),
                         ("cargo-mutants", True, False, "c0ffee1", "missing"))
        self.assertIsInstance(end["seconds"], int)

    def test_un_outil_trop_long_est_arrete_et_le_budget_est_commun(self):
        slow = ballet_mutation.Tool("slow", "echo start; sleep 30", "c", "r.json", "cargo-mutants")
        after = ballet_mutation.Tool("after", "echo never", "c", "r.json", "cargo-mutants")
        outcomes = self.run_tools(slow, after, budget=1)
        self.assertEqual([(outcome.tool, outcome.timed_out, outcome.passed) for outcome in outcomes],
                         [("slow", True, False), ("after", True, False)])
        self.assertEqual(Path(outcomes[0].log).read_text(), "start\n")


class RunByHandTest(unittest.TestCase):
    """`ballet_mutation.py run` sur un vrai repo git : le même chemin que la Rehearsal."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        state = tempfile.TemporaryDirectory()   # le dossier d'état, hors du repo
        self.addCleanup(state.cleanup)
        environment = mock.patch.dict("os.environ", {"BALLET_HOME": state.name})
        environment.start()
        self.addCleanup(environment.stop)
        self.git("init", "-q", "-b", "main")
        (self.home / "lib.rs").write_text("fn a() {}\n", encoding="utf-8")
        self.commit("init")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        (self.home / "lib.rs").write_text("fn a() {}\nfn b() {}\n", encoding="utf-8")
        self.commit("change")

    def git(self, *arguments):
        subprocess.run(["git", "-C", str(self.home), *arguments], check=True, capture_output=True)

    def commit(self, message):
        self.git("add", "-A")
        self.git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", message)

    def profile(self, command, mutation=""):
        (self.home / ".ballet").mkdir(exist_ok=True)
        (self.home / ".ballet" / "config.toml").write_text(f"""{mutation}
[project]
specs = "specs/"

[repos.app]
path = "."
proof = "true"

[[repos.app.mutation]]
name = "fake"
command = "{command}"
config = "mutants.toml"
report = {{ path = "out.json", format = "cargo-mutants" }}
""", encoding="utf-8")

    def run_by_hand(self, *arguments):
        output = io.StringIO()
        with redirect_stdout(output):
            code = ballet_mutation.main(["ballet_mutation.py", "run", *arguments], home=str(self.home))
        return code, output.getvalue()

    def test_un_outil_rouge_fait_sortir_avec_1_et_recoit_les_plages_du_diff(self):
        self.profile("echo {ranges}; exit 2")
        code, output = self.run_by_hand()
        self.assertEqual(code, 1)
        self.assertIn("fake: red (exit 2)", output)
        self.assertEqual((ballet_store.work_dir(self.home) / "manual" / "mutation-fake.log").read_text(), "lib.rs:2-2\n")
        self.assertFalse((self.home / ".ballet" / "run").exists())

    def test_un_outil_vert_sort_avec_0(self):
        self.profile("true")
        self.assertEqual(self.run_by_hand()[0], 0)

    def test_le_drapeau_du_profil_est_respecte_sauf_avec_force(self):
        self.profile("exit 2", mutation="[mutation]\nenabled = false\n")
        self.assertEqual(self.run_by_hand(), (0, "Mutation skipped: disabled in the profile ([mutation] enabled = false); --force runs it anyway.\n"))
        self.assertEqual(self.run_by_hand("--force")[0], 1)

    def test_un_usage_invalide_sort_avec_2(self):
        self.assertEqual(ballet_mutation.main(["ballet_mutation.py", "go"], home=str(self.home)), 2)


if __name__ == "__main__":
    unittest.main()
