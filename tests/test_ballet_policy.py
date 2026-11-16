import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_policy  # noqa: E402
from ballet_policy import Passage, Zones  # noqa: E402

BRANCH = "rehearsal/FEAT-001.2"
ZONES = Zones(specs="specs/", adr="docs/ADR/", sensitive=["*/contract/*"])
SPEC = 'import { it } from "vitest";\n\nit("lists the stock", () => {});\nit("sorts by deadline", () => {});\n'


class ToyRepo:
    """Un vrai repo git jetable : `main` publié comme `origin/main`, et la branche de Rehearsal ouverte dessus."""

    def __init__(self, folder):
        self.path = Path(folder)
        self.git(["init", "-q", "-b", "main"])
        self.git(["config", "user.email", "t@t"])
        self.git(["config", "user.name", "t"])
        self.commit({"src/a.ts": "a\n", "src/a.test.ts": SPEC, "AGENTS.md": "rules\n"}, "main")
        self.git(["update-ref", "refs/remotes/origin/main", "HEAD"])
        self.git(["checkout", "-q", "-b", BRANCH])

    def git(self, arguments):
        return subprocess.run(["git", "-C", str(self.path), *arguments], capture_output=True, text=True, check=True).stdout

    def write(self, files):
        for name, content in files.items():
            path = self.path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def commit(self, files, message="change"):
        self.write(files)
        self.git(["add", "-A"])
        self.git(["commit", "-q", "-m", message])
        return ballet_policy.head(self.git)

    def remove(self, name):
        self.git(["rm", "-q", name])
        self.git(["commit", "-q", "-m", "remove"])

    def passage(self, role, **fields):
        return Passage(role, BRANCH, checkpoint=ballet_policy.head(self.git), refs=ballet_policy.refs(self.git), **fields)

    def violations(self, passage):
        return ballet_policy.violations(passage, ZONES, self.git)


class BalletPolicyTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.repo = ToyRepo(folder.name)

    def test_un_dancer_qui_code_et_ajoute_ses_tests_est_en_regle(self):
        passage = self.repo.passage("dancer")
        self.repo.commit({"src/b.ts": "b\n", "src/a.test.ts": SPEC.replace('import { it }', 'import { it, expect }') + 'it("filters", () => {});\n'})
        self.assertEqual(self.repo.violations(passage), [])

    def test_le_dancer_ne_touche_ni_specs_ni_adr_ni_harnais_ni_zone_sensible(self):
        passage = self.repo.passage("dancer")
        self.repo.commit({"specs/backlog.md": "x\n", "docs/ADR/0001.md": "x\n", ".github/workflows/proof.yml": "x\n",
                          "apps/web/CLAUDE.md": "x\n", "api/contract/stock.json": "{}\n"})
        self.assertEqual(self.repo.violations(passage), [
            ".github/workflows/proof.yml: the harness, the CI or the git hooks",
            "api/contract/stock.json: a sensitive zone of [policy] sensitive_zones",
            "apps/web/CLAUDE.md: the harness, the CI or the git hooks",
            "docs/ADR/0001.md: the ADR folder",
            "specs/backlog.md: the specs space",
        ])

    def test_une_zone_interdite_annulee_par_un_commit_suivant_n_est_plus_une_violation(self):
        passage = self.repo.passage("dancer")
        self.repo.commit({"AGENTS.md": "my rules\n"})
        self.repo.commit({"AGENTS.md": "rules\n"})
        self.assertEqual(self.repo.violations(passage), [])

    def test_les_commits_du_choreographer_sur_agents_md_ne_comptent_pas_contre_le_dancer(self):
        rule = self.repo.commit({"AGENTS.md": "rules\nand one more\n", "docs/ADR/0002.md": "adr\n"})
        passage = self.repo.passage("dancer", owned=[rule])
        self.repo.commit({"src/b.ts": "b\n"})
        self.assertEqual(self.repo.violations(passage), [])

    def test_le_dancer_qui_retouche_agents_md_apres_le_choreographer_est_en_violation(self):
        rule = self.repo.commit({"AGENTS.md": "rules\nand one more\n"})
        passage = self.repo.passage("dancer", owned=[rule])
        self.repo.commit({"AGENTS.md": "rules\nand mine\n"})
        self.assertEqual(self.repo.violations(passage), ["AGENTS.md: the harness, the CI or the git hooks"])

    def test_un_test_existant_supprime_ou_renomme_est_une_violation(self):
        passage = self.repo.passage("dancer")
        self.repo.commit({"src/a.test.ts": SPEC.replace("sorts by deadline", "sorts")})
        self.assertEqual(self.repo.violations(passage), ["src/a.test.ts: existing test removed or renamed: sorts by deadline"])

    def test_un_fichier_de_tests_existant_supprime_perd_tous_ses_tests(self):
        passage = self.repo.passage("dancer")
        self.repo.remove("src/a.test.ts")
        self.assertEqual(len(self.repo.violations(passage)), 2)

    def test_un_test_cree_sur_la_branche_peut_y_etre_renomme(self):
        passage = self.repo.passage("dancer")
        self.repo.commit({"src/b.test.ts": 'it("first name", () => {});\n'})
        self.repo.commit({"src/b.test.ts": 'it("better name", () => {});\n'})
        self.assertEqual(self.repo.violations(passage), [])

    def test_reconnait_les_tests_rust_python_et_gherkin(self):
        rust = "#[test]\nfn keeps_days() {}\n\n#[tokio::test]\n#[ignore]\nasync fn reads() {}\n"
        python = "def test_reads():\n    pass\n\ndef helper():\n    pass\n"
        gherkin = "Feature: Stock\n  Scenario: Empty stock\n  Scenario Outline: A status <s>\n"
        self.assertEqual(sorted(ballet_policy._test_names("lib.rs", rust)), ["keeps_days", "reads"])
        self.assertEqual(sorted(ballet_policy._test_names("test_a.py", python)), ["test_reads"])
        self.assertEqual(sorted(ballet_policy._test_names("a.feature", gherkin)), ["A status <s>", "Empty stock"])

    def test_tout_role_laisse_un_arbre_propre(self):
        passage = self.repo.passage("dancer")
        self.repo.write({"src/c.ts": "c\n"})
        self.assertEqual(self.repo.violations(passage), ["uncommitted changes left in the worktree: src/c.ts"])

    def test_tout_role_reste_sur_la_branche_de_rehearsal(self):
        passage = self.repo.passage("dancer")
        self.repo.git(["checkout", "-q", "main"])
        self.assertIn("the worktree is on `main`, not on `rehearsal/FEAT-001.2`", self.repo.violations(passage))

    def test_une_reecriture_d_historique_est_une_violation(self):
        self.repo.commit({"src/b.ts": "b\n"})
        passage = self.repo.passage("dancer")
        self.repo.git(["reset", "-q", "--hard", "HEAD~1"])
        self.assertEqual(self.repo.violations(passage)[0][:36], "history rewritten: 1 commit(s) befor")

    def test_une_branche_creee_ou_supprimee_est_une_violation(self):
        self.repo.git(["branch", "old"])
        passage = self.repo.passage("dancer")
        self.repo.git(["branch", "-D", "old"])
        self.repo.git(["tag", "v1"])
        self.assertEqual(self.repo.violations(passage), ["branch or tag created: refs/tags/v1", "branch or tag deleted: refs/heads/old"])

    def test_le_critic_ne_bouge_pas_head(self):
        passage = self.repo.passage("critic")
        self.assertEqual(self.repo.violations(passage), [])
        self.repo.commit({"src/a.ts": "fixed\n"})
        self.assertEqual(len(self.repo.violations(passage)), 1)

    def test_le_choreographer_n_ecrit_que_les_adr_et_agents_md_et_peut_ouvrir_un_spike(self):
        passage = self.repo.passage("choreographer")
        self.repo.commit({"docs/ADR/0002.md": "adr\n", "AGENTS.md": "rules\nmore\n"})
        self.repo.git(["branch", "spike/02-wasm"])
        self.assertEqual(self.repo.violations(passage), [])
        self.repo.commit({"src/a.ts": "mine\n"})
        self.assertEqual(self.repo.violations(passage), ["src/a.ts: the Choreographer writes only ADRs and AGENTS.md"])

    def test_le_choreographer_qui_repond_laisse_l_arbre_du_dancer_en_cours(self):
        self.repo.write({"src/wip.ts": "wip\n"})
        passage = self.repo.passage("choreographer", answering=True)
        self.repo.write({"docs/ADR/0002.md": "adr\n"})
        self.repo.git(["add", "docs"])
        self.repo.git(["commit", "-q", "-m", "adr"])
        self.assertEqual(self.repo.violations(passage), [])

    def test_la_ligne_de_commande_audite_la_branche_comme_un_dancer(self):
        (self.repo.path / ".ballet").mkdir()
        (self.repo.path / ".ballet" / "config.toml").write_text('[project]\nspecs = "specs/"\n', encoding="utf-8")
        self.repo.git(["add", "-A"])
        self.repo.git(["commit", "-q", "-m", "profile"])
        self.assertEqual(ballet_policy.main(["ballet_policy.py", str(self.repo.path), str(self.repo.path)]), 1)


if __name__ == "__main__":
    unittest.main()
