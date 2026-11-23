import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_github  # noqa: E402

ISSUE_BODY = "## Context\n\nWhy.\n\n## Plan\n\n<!-- empty -->\n\n## Notes\n\nKeep me.\n"

PULL_REQUEST = {
    "title": "FEAT-001.1 · Walking skeleton",
    "body": "Closes #2",
    "reviews": [{"author": {"login": "bilel"}, "state": "COMMENTED", "body": "VERDICT: REJECTED\n\n1. Fix it.", "submittedAt": "2026-11-16T10:00:00Z"}],
    "comments": [
        {"author": {"login": "bilel"}, "body": "Dancer report", "createdAt": "2026-11-16T09:00:00Z"},
        {"author": {"login": "bilel"}, "body": "Dancer report, round 2", "createdAt": "2026-11-16T11:00:00Z"},
    ],
}


VERDICT_HEADER = '{"ballet": "message", "from": "critic", "to": "conductor", "type": "verdict", "subject": "#2", "round": 1}'
REPORT_HEADER = '{"ballet": "message", "from": "dancer", "to": "conductor", "type": "report", "subject": "#2", "round": 1}'

GREEN_CHECK = {"__typename": "CheckRun", "name": "proof", "status": "COMPLETED", "conclusion": "SUCCESS"}
RED_CHECK = {"__typename": "CheckRun", "name": "proof", "status": "COMPLETED", "conclusion": "FAILURE"}


def mergeable_pull_request(verdict="APPROVED", checks=(GREEN_CHECK,), reviewed_at="2026-11-16T12:00:00Z"):
    return {
        "headRefName": "rehearsal/FEAT-001.1",
        "reviews": [
            {"author": {"login": "bilel"}, "body": f"{VERDICT_HEADER}\n\nVERDICT: REJECTED\n\n1. Fix it.", "submittedAt": "2026-11-16T10:00:00Z"},
            {"author": {"login": "bilel"}, "body": f"{VERDICT_HEADER}\n\nVERDICT: {verdict}\n", "submittedAt": reviewed_at},
        ],
        "commits": [{"committedDate": "2026-11-16T11:00:00Z"}],
        "statusCheckRollup": list(checks),
    }


def labeled(name, at, kind="labeled"):
    return {"event": kind, "label": {"name": name}, "created_at": at}


APPROVED_TIMELINE = [labeled("ballet:rejected", "2026-11-16T10:00:00Z"), labeled("ballet:rejected", "2026-11-16T12:00:00Z", "unlabeled"),
                     labeled("ballet:approved", "2026-11-16T12:00:00Z")]


PR_DIFF = """diff --git a/e2e/package.json b/e2e/package.json
--- a/e2e/package.json
+++ b/e2e/package.json
@@ -14,3 +14,3 @@
   "x": 1,
-  "wrangler": "4",
+  "y": 2
 }
diff --git a/apps/worker/vitest.config.ts b/apps/worker/vitest.config.ts
new file mode 100644
--- /dev/null
+++ b/apps/worker/vitest.config.ts
@@ -0,0 +1,3 @@
+import a from "a";
+
+export default a;
"""

API_REVIEWS = [
    {"id": 11, "user": {"login": "bilel"}, "body": "VERDICT: REJECTED\n\n## Blocking\n\n1. `e2e/package.json:15` (inline comment)", "submitted_at": "2026-11-16T10:00:00Z"},
]

API_REVIEW_COMMENTS = [
    {"pull_request_review_id": 11, "path": "e2e/package.json", "line": 15, "start_line": None, "body": "**Blocking 1** — Unused dependency."},
]

VERDICT_WITH_PLACES = f"""{VERDICT_HEADER}

VERDICT: REJECTED

- Proof: `pnpm proof` green.

## Blocking

1. `e2e/package.json:15` — `wrangler` is not in the plan. Ref: Decisions.
   Expected: remove it.
2. `apps/worker/src/main.ts:99` — Out of the diff. Ref: task 3.

## Notes

- `apps/worker/vitest.config.ts:1-3`: the filter is too wide.
- A note without a place.
"""


STATUS_OPTIONS = ["proposed", "ready", "in-rehearsal", "plan-review", "escalated", "done"]


def status_answer(fields=None):
    """La réponse de GitHub à la lecture de l'issue et des champs de son propriétaire."""
    fields = {"Ballet status": STATUS_OPTIONS} if fields is None else fields
    nodes = [{"id": f"FIELD-{name}", "name": name, "options": [{"id": f"OPT-{option}", "name": option} for option in options]}
             for name, options in fields.items()]
    return json.dumps({"data": {"repository": {"issue": {"id": "ISSUE-42"}}, "repositoryOwner": {"issueFields": {"nodes": nodes}}}})


def created_by(gh):
    """L'appel qui a créé l'issue : la publication lit d'abord les issues du repo quand le brouillon a un identifiant."""
    return next(call for call in gh.calls if call[:2] == ["issue", "create"])


def status_mutation(gh):
    return next(call for call in gh.calls if any("setIssueFieldValue" in argument for argument in call))


class FakeGh:
    def __init__(self, body=ISSUE_BODY, pull_request=PULL_REQUEST, timeline=(), fields=None):
        self.issues = []          # les issues du repo, telles que `gh issue list` les rend
        self.blocked_by = {}      # numéro → numéros qui le bloquent déjà
        self.links = []           # (bloquée, bloqueur) posés par addBlockedBy ; (…, "-") retirés par removeBlockedBy
        self.missing = set()      # des numéros d'issue que GitHub ne connaît pas
        self.link_failure = ""    # le message d'erreur d'addBlockedBy / removeBlockedBy
        self.fields = fields
        self.mutation_reply = "{}"
        self.body = body
        self.pull_request = pull_request
        self.timeline = [{"event": "commented"}, *timeline]
        self.calls = []
        self.posted_reviews = []

    def __call__(self, arguments):
        self.calls.append(arguments)
        if arguments[:2] == ["issue", "view"]:
            return json.dumps({"body": self.body, "title": "FEAT-001.1 · Walking skeleton"})
        if arguments[:2] == ["issue", "create"]:
            return "https://github.com/o/r/issues/42\n"
        if arguments[:2] == ["issue", "list"] and "--state" in arguments and "number,title,body,state" in arguments:
            return json.dumps(self.issues)
        if arguments[:2] == ["api", "graphql"] and any("blocker: issue" in a for a in arguments):
            return self.pair_answer(arguments)
        if arguments[:2] == ["api", "graphql"] and any("BlockedBy(input" in a for a in arguments):
            return self.change_link(arguments)
        if arguments[:2] == ["api", "graphql"] and any(a.startswith("query=query") for a in arguments):
            return status_answer(self.fields)
        if arguments[:2] == ["api", "graphql"]:
            return self.mutation_reply
        if arguments[:2] == ["pr", "create"]:
            return "https://github.com/o/r/pull/43\n"
        if arguments[:2] == ["pr", "view"] and arguments[-1] == "labels":
            return json.dumps({"labels": [{"name": name} for name in self.labels()]})
        if arguments[:2] == ["pr", "view"]:
            return json.dumps(self.pull_request)
        if arguments[:2] == ["pr", "diff"]:
            return PR_DIFF
        if arguments[0] == "api" and arguments[1].endswith("/timeline"):
            return json.dumps([self.timeline])
        if arguments[0] == "api" and "--input" in arguments:
            self.posted_reviews.append(json.loads(Path(arguments[arguments.index("--input") + 1]).read_text()))
            return "{}"
        if arguments[0] == "api" and arguments[1].endswith("/reviews"):
            return json.dumps([API_REVIEWS])
        if arguments[0] == "api" and arguments[1].endswith("/comments"):
            return json.dumps([API_REVIEW_COMMENTS])
        if arguments[:2] == ["issue", "edit"]:
            self.body = arguments[arguments.index("--body") + 1]
        return ""

    def pair_answer(self, arguments):
        issue, blocker = (next(a for a in arguments if a.startswith(f"{name}=")).split("=")[1] for name in ("issue", "blocker"))
        node = lambda found: {"id": f"ID-{found}", "blockedBy": {"nodes": [{"number": int(n)} for n in self.blocked_by.get(found, [])]}}
        known = lambda found: found not in self.missing
        return json.dumps({"data": {"repository": {"issue": node(issue) if known(issue) else None,
                                                   "blocker": node(blocker) if known(blocker) else None}}})

    def change_link(self, arguments):
        query = next(a for a in arguments if a.startswith("query="))
        issue, blocker = (next(a for a in arguments if a.startswith(f"{name}=")).split("=")[1][3:] for name in ("issue", "blocker"))
        if self.link_failure:
            return json.dumps({"errors": [{"message": self.link_failure}]})
        self.links.append((issue, blocker) if "addBlockedBy" in query else (issue, blocker, "-"))
        return "{}"

    def labels(self):
        on_the_pr = set()
        for event in self.timeline:
            if event.get("event") in ("labeled", "unlabeled"):
                (on_the_pr.add if event["event"] == "labeled" else on_the_pr.discard)(event["label"]["name"])
        return sorted(on_the_pr)


class FakeGit:
    def __init__(self):
        self.calls = []

    def __call__(self, arguments):
        self.calls.append(arguments)
        return ""


class BalletGitHubTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def file(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_publie_un_brouillon_avec_son_titre(self):
        gh = FakeGh()
        draft = self.file("d.md", "# FEAT-001 · Sign in\n\n## Context\n\nWhy.\n")
        self.assertEqual(ballet_github.publish_issue(draft, "Feature", "ready", run=gh), "42")
        create = created_by(gh)
        self.assertEqual(create[create.index("--title") + 1], "FEAT-001 · Sign in")
        self.assertTrue(create[create.index("--body") + 1].startswith("## Context"))

    def test_publie_l_issue_a_son_type_natif(self):
        gh = FakeGh()
        ballet_github.publish_issue(self.file("d.md", "# BUG-002 · Lost basket\n\n## Context\n\nWhy.\n"), "Bug", "ready", run=gh)
        create = created_by(gh)
        self.assertEqual(create[create.index("--type") + 1], "Bug")

    def test_pose_le_statut_ballet_de_l_issue_publiee(self):
        gh = FakeGh()
        ballet_github.publish_issue(self.file("d.md", "# FEAT-001 · Sign in\n\n## Context\n\nWhy.\n"), "Feature", "proposed", run=gh)
        mutation = status_mutation(gh)
        self.assertIn("issue=ISSUE-42", mutation)
        self.assertIn("field=FIELD-Ballet status", mutation)
        self.assertIn("option=OPT-proposed", mutation)

    def test_ajoute_une_section_plan_vide_quand_le_brouillon_n_en_a_pas(self):
        gh = FakeGh()
        ballet_github.publish_issue(self.file("d.md", "# FEAT-001 · Sign in\n\n## Context\n\nWhy.\n"), "Feature", "ready", run=gh)
        body = created_by(gh)[created_by(gh).index("--body") + 1]
        self.assertIn("## Plan\n\n_The Choreographer writes the plan here._", body)

    def test_garde_la_section_plan_d_un_brouillon_qui_en_a_une(self):
        gh = FakeGh()
        ballet_github.publish_issue(self.file("d.md", "# BUG-002 · x\n\n## Plan\n\n- a → b.\n"), "Bug", "ready", run=gh)
        body = created_by(gh)[created_by(gh).index("--body") + 1]
        self.assertEqual(body.count("## Plan"), 1)
        self.assertNotIn("Choreographer writes", body)

    def test_le_plan_se_range_ensuite_dans_la_section_publiee(self):
        gh = FakeGh()
        ballet_github.publish_issue(self.file("d.md", "# FEAT-001 · Sign in\n\n## Context\n\nWhy.\n"), "Feature", "ready", run=gh)
        gh.body = created_by(gh)[created_by(gh).index("--body") + 1]
        ballet_github.write_plan("42", self.file("p.md", "## Plan\n\n### Decisions\n\n- a → b.\n"), run=gh)
        self.assertIn("- a → b.", gh.body)
        self.assertNotIn("Choreographer writes", gh.body)

    def test_refuse_un_type_inconnu_et_n_ecrit_rien(self):
        gh = FakeGh()
        with self.assertRaisesRegex(ballet_github.GitHubError, "unknown issue type 'Slice'"):
            ballet_github.publish_issue(self.file("d.md", "# T\n\nx\n"), "Slice", "ready", run=gh)
        self.assertEqual(gh.calls, [])

    def test_refuse_un_statut_inconnu_et_n_ecrit_rien(self):
        gh = FakeGh()
        with self.assertRaisesRegex(ballet_github.GitHubError, "unknown Ballet status 'wip'"):
            ballet_github.publish_issue(self.file("d.md", "# T\n\nx\n"), "Feature", "wip", run=gh)
        self.assertEqual(gh.calls, [])

    def test_sans_champ_ballet_status_l_erreur_nomme_l_issue_et_init_project(self):
        gh = FakeGh(fields={})
        with self.assertRaisesRegex(ballet_github.GitHubError, r"issue #42 was created.*init-project"):
            ballet_github.publish_issue(self.file("d.md", "# T\n\nx\n"), "Feature", "ready", run=gh)

    def test_pose_le_mode_de_rehearsal_demande_a_la_publication(self):
        gh = FakeGh(fields={"Ballet status": STATUS_OPTIONS, "Rehearsal mode": ["assisted", "autopilot"]})
        ballet_github.publish_issue(self.file("d.md", "# FEAT-001 · Sign in\n\nx\n"), "Feature", "ready", run=gh, mode="autopilot")
        mutations = [call for call in gh.calls if any("setIssueFieldValue" in argument for argument in call)]
        self.assertIn("field=FIELD-Rehearsal mode", mutations[-1])
        self.assertIn("option=OPT-autopilot", mutations[-1])

    def test_sans_mode_demande_la_publication_ne_touche_pas_au_champ(self):
        gh = FakeGh()
        ballet_github.publish_issue(self.file("d.md", "# FEAT-001 · Sign in\n\nx\n"), "Feature", "ready", run=gh)
        mutations = [call for call in gh.calls if any("setIssueFieldValue" in argument for argument in call)]
        self.assertEqual(len(mutations), 1)

    def test_refuse_un_mode_inconnu_et_n_ecrit_rien(self):
        gh = FakeGh()
        with self.assertRaisesRegex(ballet_github.GitHubError, "unknown Rehearsal mode 'night'"):
            ballet_github.publish_issue(self.file("d.md", "# T\n\nx\n"), "Feature", "ready", run=gh, mode="night")
        self.assertEqual(gh.calls, [])

    def test_sans_champ_rehearsal_mode_l_erreur_nomme_l_issue_et_init_project(self):
        gh = FakeGh()
        with self.assertRaisesRegex(ballet_github.GitHubError, r"issue #42 was created.*Rehearsal mode.*init-project"):
            ballet_github.publish_issue(self.file("d.md", "# T\n\nx\n"), "Feature", "ready", run=gh, mode="autopilot")

    def test_pose_le_mode_d_une_issue_existante(self):
        gh = FakeGh(fields={"Ballet status": STATUS_OPTIONS, "Rehearsal mode": ["assisted", "autopilot"]})
        ballet_github.set_mode("#42", "autopilot", run=gh)
        self.assertIn("field=FIELD-Rehearsal mode", gh.calls[-1])
        self.assertIn("option=OPT-autopilot", gh.calls[-1])

    def test_publish_en_ligne_de_commande_accepte_mode(self):
        self.assertEqual(ballet_github._publish_options(["--mode", "autopilot"]), "autopilot")
        self.assertIsNone(ballet_github._publish_options([]))
        with self.assertRaisesRegex(ballet_github.GitHubError, "usage: publish"):
            ballet_github._publish_options(["--fast"])

    def test_pose_le_statut_d_une_issue_existante(self):
        gh = FakeGh()
        ballet_github.set_status("#42", "in-rehearsal", run=gh)
        self.assertIn("option=OPT-in-rehearsal", gh.calls[-1])
        self.assertIn("number=42", gh.calls[0])

    def test_refuse_de_poser_un_statut_inconnu(self):
        gh = FakeGh()
        with self.assertRaisesRegex(ballet_github.GitHubError, "unknown Ballet status 'wip'"):
            ballet_github.set_status("42", "wip", run=gh)
        self.assertEqual(gh.calls, [])

    def test_lit_le_type_le_mode_l_approbation_du_plan_et_le_statut_d_une_issue(self):
        values = [{"name": "assisted", "field": {"name": "Rehearsal mode"}}, {"name": "skipped", "field": {"name": "Plan approval"}},
                  {"name": "ready", "field": {"name": "Ballet status"}}, {}]
        answer = {"data": {"repository": {"issue": {"issueType": {"name": "Bug"}, "issueFieldValues": {"nodes": values}}}}}
        calls = []

        def gh(arguments):
            calls.append(arguments)
            return json.dumps(answer)
        self.assertEqual(ballet_github.queue_fields("#12", run=gh),
                         {"type": "Bug", "mode": "assisted", "plan_approval": "skipped", "status": "ready"})
        self.assertIn("number=12", calls[0])

    def test_une_issue_sans_type_ni_champ_se_lit_vide(self):
        answer = {"data": {"repository": {"issue": {"issueType": None, "issueFieldValues": {"nodes": []}}}}}
        self.assertEqual(ballet_github.queue_fields("12", run=lambda arguments: json.dumps(answer)),
                         {"type": "", "mode": "", "plan_approval": "", "status": ""})

    def test_un_refus_de_github_sur_le_champ_nomme_l_issue(self):
        gh = FakeGh()
        gh.mutation_reply = json.dumps({"errors": [{"message": "Resource not accessible"}]})
        with self.assertRaisesRegex(ballet_github.GitHubError, r"issue #42 was created.*Resource not accessible"):
            ballet_github.publish_issue(self.file("d.md", "# T\n\nx\n"), "Feature", "ready", run=gh)

    def test_refuse_un_brouillon_sans_titre(self):
        with self.assertRaises(ballet_github.GitHubError):
            ballet_github.publish_issue(self.file("d.md", "no title\n"), "Feature", "ready", run=FakeGh())

    def test_ecrit_le_plan_dans_sa_section_sans_toucher_au_reste(self):
        gh = FakeGh()
        plan = self.file("p.md", "## Plan\n\n### Decisions\n\n- a → b.\n")
        ballet_github.write_plan("#7", plan, run=gh)
        self.assertIn("## Plan\n\n### Decisions\n\n- a → b.\n\n## Notes\n\nKeep me.", gh.body)
        self.assertNotIn("<!-- empty -->", gh.body)
        self.assertEqual(gh.body.count("## Plan"), 1)

    def test_refuse_une_issue_sans_section_plan(self):
        gh = FakeGh(body="## Context\n")
        with self.assertRaises(ballet_github.GitHubError):
            ballet_github.write_plan("7", self.file("p.md", "x"), run=gh)

    def test_refuse_un_brouillon_complet_a_la_place_du_plan(self):
        gh = FakeGh()
        draft = self.file("d.md", "# FEAT-001 · Sign in\n\n## Plan\n\n- a → b.\n")
        with self.assertRaisesRegex(ballet_github.GitHubError, "publish"):
            ballet_github.write_plan("7", draft, run=gh)
        self.assertFalse([call for call in gh.calls if call[:2] == ["issue", "edit"]])

    def test_un_brouillon_sans_titre_renvoie_vers_plan(self):
        with self.assertRaisesRegex(ballet_github.GitHubError, "plan"):
            ballet_github.publish_issue(self.file("d.md", "## Plan\n\n- a → b.\n"), "Feature", "ready", run=FakeGh())

    def test_une_slice_pointe_vers_sa_parente(self):
        gh = FakeGh()
        draft = self.file("s.md", "# FEAT-001.1 · Skeleton\n\n## Plan\n\nx\n")
        self.assertEqual(ballet_github.publish_slice("#7", draft, run=gh), "42")
        body = gh.calls[0][gh.calls[0].index("--body") + 1]
        self.assertTrue(body.startswith("Part of #7\n"))

    def test_une_slice_est_de_type_slice_et_n_a_pas_de_statut(self):
        gh = FakeGh()
        ballet_github.publish_slice("#7", self.file("s.md", "# FEAT-001.1 · Skeleton\n\n## Plan\n\nx\n"), run=gh)
        self.assertEqual(gh.calls[0][gh.calls[0].index("--type") + 1], "Slice")
        self.assertFalse([call for call in gh.calls if call[:2] == ["api", "graphql"]])

    def test_lit_une_pr_avec_ses_reviews_et_commentaires_dans_l_ordre(self):
        text = ballet_github.read_pull_request("#5", run=FakeGh())
        self.assertTrue(text.startswith("# PR #5 · FEAT-001.1 · Walking skeleton\n\nCloses #2"))
        first, review, second = (text.index("Dancer report\n"), text.index("VERDICT: REJECTED"), text.index("round 2"))
        self.assertLess(first, review)
        self.assertLess(review, second)
        self.assertIn("## Review · bilel · 2026-11-16T10:00:00Z", text)

    def test_lit_les_commentaires_en_ligne_sous_leur_review(self):
        text = ballet_github.read_pull_request("5", run=FakeGh())
        review, inline, second = (text.index("VERDICT: REJECTED"), text.index("### `e2e/package.json:15`"), text.index("round 2"))
        self.assertLess(review, inline)
        self.assertLess(inline, second)
        self.assertIn("**Blocking 1** — Unused dependency.", text)

    def test_publie_chaque_point_situe_dans_le_diff_en_commentaire_sur_sa_ligne(self):
        gh = FakeGh()
        ballet_github.publish_review("#43", self.file("v.md", VERDICT_WITH_PLACES), run=gh)
        review = gh.posted_reviews[-1]
        self.assertEqual(review["event"], "COMMENT")
        self.assertEqual(review["comments"], [
            {"path": "e2e/package.json", "line": 15, "side": "RIGHT",
             "body": "**Blocking 1** — `wrangler` is not in the plan. Ref: Decisions.\nExpected: remove it."},
            {"path": "apps/worker/vitest.config.ts", "start_line": 1, "start_side": "RIGHT", "line": 3, "side": "RIGHT",
             "body": "**Note** — the filter is too wide."},
        ])

    def test_garde_dans_la_review_le_verdict_et_les_points_hors_du_diff(self):
        gh = FakeGh()
        ballet_github.publish_review("43", self.file("v.md", VERDICT_WITH_PLACES), run=gh)
        body = gh.posted_reviews[-1]["body"]
        self.assertTrue(body.startswith(VERDICT_HEADER + "\n\nVERDICT: REJECTED"))
        self.assertIn("1. `e2e/package.json:15` (inline comment)", body)
        self.assertIn("2. `apps/worker/src/main.ts:99` — Out of the diff. Ref: task 3.", body)
        self.assertIn("- A note without a place.", body)
        self.assertNotIn("Expected: remove it.", body)

    def test_pousse_la_branche_de_rehearsal(self):
        git = FakeGit()
        ballet_github.push_branch("rehearsal/FEAT-001.1", git=git)
        self.assertEqual(git.calls, [["push", "--set-upstream", "origin", "rehearsal/FEAT-001.1"]])

    def test_refuse_de_pousser_une_autre_branche_que_celle_d_une_rehearsal(self):
        for branch in ("main", "spike/01-wasm", "rehearsal/oops", "rehearsal/FEAT-001;rm"):
            with self.subTest(branch=branch), self.assertRaises(ballet_github.GitHubError):
                ballet_github.push_branch(branch, git=FakeGit())

    def test_ouvre_la_pr_sur_main_liee_a_l_issue(self):
        gh = FakeGh()
        self.assertEqual(ballet_github.open_pull_request("#2", "rehearsal/FEAT-001.1", run=gh), "43")
        create = gh.calls[-1]
        self.assertEqual(create[create.index("--base") + 1], "main")
        self.assertEqual(create[create.index("--head") + 1], "rehearsal/FEAT-001.1")
        self.assertEqual(create[create.index("--title") + 1], "FEAT-001.1 · Walking skeleton")
        self.assertEqual(create[create.index("--body") + 1], "Closes #2\n")

    def test_refuse_d_ouvrir_une_pr_depuis_une_autre_branche(self):
        with self.assertRaises(ballet_github.GitHubError):
            ballet_github.open_pull_request("2", "main", run=FakeGh())

    def test_pousse_aussi_la_branche_d_un_workshop(self):
        git = FakeGit()
        ballet_github.push_branch("workshop/BUG-004", git=git)
        self.assertEqual(git.calls, [["push", "--set-upstream", "origin", "workshop/BUG-004"]])

    def test_pousse_la_branche_d_un_workshop_sur_une_demande_nommee_par_son_slug(self):
        git = FakeGit()
        ballet_github.push_branch("workshop/le-stock-passe-en-negatif", git=git)
        self.assertEqual(git.calls, [["push", "--set-upstream", "origin", "workshop/le-stock-passe-en-negatif"]])

    def test_refuse_de_pousser_une_branche_de_workshop_qui_n_est_ni_une_ligne_ni_un_slug(self):
        for branch in ("workshop/Oops", "workshop/CAP-001", "workshop/BUG-004;rm", "workshop/", "workshop/-x", "workshop/a--b", "workshop/a b"):
            with self.subTest(branch=branch), self.assertRaises(ballet_github.GitHubError):
                ballet_github.push_branch(branch, git=FakeGit())

    def test_la_pr_des_specs_d_un_workshop_ne_ferme_aucune_issue(self):
        gh = FakeGh()
        self.assertEqual(ballet_github.open_specs_pull_request("workshop/BUG-004", run=gh), "43")
        create = gh.calls[-1]
        self.assertEqual(create[create.index("--base") + 1], "main")
        self.assertEqual(create[create.index("--head") + 1], "workshop/BUG-004")
        self.assertEqual(create[create.index("--title") + 1], "docs(specs): BUG-004")
        self.assertNotIn("Closes", create[create.index("--body") + 1])

    def test_refuse_d_ouvrir_la_pr_des_specs_depuis_une_branche_de_rehearsal(self):
        with self.assertRaises(ballet_github.GitHubError):
            ballet_github.open_specs_pull_request("rehearsal/FEAT-001.1", run=FakeGh())

    def test_merge_les_specs_d_un_workshop_sans_verdict_puis_supprime_la_branche(self):
        gh, git = FakeGh(pull_request={**mergeable_pull_request(), "headRefName": "workshop/BUG-004"}), FakeGit()
        ballet_github.merge_specs_pull_request("#43", run=gh, git=git)
        self.assertEqual(gh.calls[-1], ["pr", "merge", "43", "--rebase"])
        self.assertEqual(git.calls, [["push", "origin", "--delete", "workshop/BUG-004"]])

    def test_ne_merge_pas_sans_verdict_une_branche_de_rehearsal(self):
        gh, git = FakeGh(pull_request=mergeable_pull_request()), FakeGit()
        with self.assertRaisesRegex(ballet_github.GitHubError, "not a Workshop branch"):
            ballet_github.merge_specs_pull_request("43", run=gh, git=git)
        self.assertFalse([call for call in gh.calls if call[:2] == ["pr", "merge"]])
        self.assertEqual(git.calls, [])

    def test_merge_les_specs_d_un_workshop_sans_attendre_la_ci(self):
        specs = {"headRefName": "workshop/BUG-004"}
        running = {**GREEN_CHECK, "status": "IN_PROGRESS", "conclusion": ""}
        for case, checks in {"no CI": (), "red": (RED_CHECK,), "running": (running,)}.items():
            with self.subTest(case=case):
                gh = FakeGh(pull_request={**mergeable_pull_request(checks=checks), **specs})
                ballet_github.merge_specs_pull_request("43", run=gh, git=FakeGit())
                self.assertEqual(gh.calls[-1], ["pr", "merge", "43", "--rebase"])

    def test_un_verdict_sans_point_situe_reste_une_review_sans_commentaire(self):
        gh = FakeGh()
        verdict = f"{VERDICT_HEADER}\n\nVERDICT: APPROVED\n\n- Proof: green.\n"
        ballet_github.publish_review("#43", self.file("v.md", verdict), run=gh)
        self.assertEqual(gh.posted_reviews[-1], {"body": verdict, "event": "COMMENT", "comments": []})

    def test_refuse_une_review_qui_n_est_pas_un_verdict(self):
        for text in (f"{REPORT_HEADER}\n\nVERDICT: APPROVED\n", f"{VERDICT_HEADER}\n\nLooks good.\n", "VERDICT: APPROVED\n"):
            with self.subTest(text=text), self.assertRaises(ballet_github.GitHubError):
                ballet_github.publish_review("43", self.file("v.md", text), run=FakeGh())

    def test_commente_l_issue_et_la_pr_avec_le_message_entier(self):
        gh = FakeGh()
        message = f"{REPORT_HEADER}\n\nAll 7 tasks done.\n"
        ballet_github.comment_issue("#2", self.file("m.md", message), run=gh)
        ballet_github.comment_pull_request("#43", self.file("m.md", message), run=gh)
        self.assertEqual(gh.calls[0], ["issue", "comment", "2", "--body", message])
        self.assertEqual(gh.calls[1], ["pr", "comment", "43", "--body", message])

    def test_refuse_un_commentaire_sans_en_tete_de_message(self):
        with self.assertRaises(ballet_github.GitHubError):
            ballet_github.comment_issue("2", self.file("m.md", "hello\n"), run=FakeGh())

    def test_merge_par_rebase_puis_supprime_la_branche(self):
        gh, git = FakeGh(pull_request=mergeable_pull_request(), timeline=APPROVED_TIMELINE), FakeGit()
        ballet_github.merge_pull_request("#43", run=gh, git=git)
        self.assertEqual(gh.calls[-1], ["pr", "merge", "43", "--rebase"])
        self.assertEqual(git.calls, [["push", "origin", "--delete", "rehearsal/FEAT-001.1"]])

    def test_le_libelle_fait_foi_et_non_la_review_du_critic(self):
        gh, git = FakeGh(pull_request=mergeable_pull_request(verdict="ESCALATE"), timeline=APPROVED_TIMELINE), FakeGit()
        ballet_github.merge_pull_request("43", run=gh, git=git)
        self.assertEqual(gh.calls[-1], ["pr", "merge", "43", "--rebase"])

    def test_refuse_de_merger_sans_libelle_approved_en_vigueur(self):
        timelines = {
            "none": [],
            "rejected": [labeled("ballet:rejected", "2026-11-16T12:00:00Z")],
            "removed": [*APPROVED_TIMELINE, labeled("ballet:approved", "2026-11-16T12:30:00Z", "unlabeled")],
            "later escalation": [*APPROVED_TIMELINE, labeled("ballet:escalated", "2026-11-16T12:30:00Z")],
        }
        for case, timeline in timelines.items():
            with self.subTest(case=case):
                self.assert_merge_refused(mergeable_pull_request(), "not ballet:approved", timeline)

    def test_refuse_de_merger_une_approbation_plus_ancienne_que_le_dernier_commit(self):
        self.assert_merge_refused(mergeable_pull_request(), "commit", [labeled("ballet:approved", "2026-11-16T10:30:00Z")])

    def test_refuse_de_merger_sans_ci_ou_avec_une_ci_rouge(self):
        self.assert_merge_refused(mergeable_pull_request(checks=()), "no CI")
        self.assert_merge_refused(mergeable_pull_request(checks=(GREEN_CHECK, RED_CHECK)), "proof")

    def test_une_ci_en_cours_se_distingue_d_une_ci_rouge(self):
        running = {**GREEN_CHECK, "status": "IN_PROGRESS", "conclusion": ""}
        with self.assertRaisesRegex(ballet_github.CiPending, "still running: proof"):
            ballet_github.merge_pull_request("43", run=FakeGh(pull_request=mergeable_pull_request(checks=(GREEN_CHECK, running)), timeline=APPROVED_TIMELINE), git=FakeGit())
        with self.assertRaises(ballet_github.GitHubError) as raised:
            ballet_github.merge_pull_request("43", run=FakeGh(pull_request=mergeable_pull_request(checks=(running, RED_CHECK)), timeline=APPROVED_TIMELINE), git=FakeGit())
        self.assertNotIsInstance(raised.exception, ballet_github.CiPending)

    def test_label_cree_les_libelles_pose_le_verdict_et_retire_les_autres(self):
        gh = FakeGh()
        ballet_github.label_pull_request("#43", "approved", run=gh)
        self.assertEqual(len([call for call in gh.calls if call[:2] == ["label", "create"]]), 3)
        self.assertEqual(gh.calls[-1], ["pr", "edit", "43", "--add-label", "ballet:approved",
                                        "--remove-label", "ballet:rejected", "--remove-label", "ballet:escalated"])

    def test_decided_alone_cree_le_libelle_puis_le_pose_sur_l_issue(self):
        calls = []
        ballet_github.mark_decided_alone("#21", run=lambda arguments: calls.append(arguments) or "")
        self.assertEqual([call[:3] for call in calls], [["label", "create", "ballet:decided-alone"], ["issue", "edit", "21"]])
        self.assertEqual(calls[-1][3:], ["--add-label", "ballet:decided-alone"])

    def test_decided_alone_refuse_un_numero_d_issue_invalide(self):
        with self.assertRaises(ballet_github.GitHubError):
            ballet_github.mark_decided_alone("twenty", run=lambda arguments: "")

    def test_un_libelle_deja_pose_est_retire_puis_repose_pour_dater_le_nouveau_verdict(self):
        gh = FakeGh(timeline=[labeled("ballet:approved", "2026-11-16T10:00:00Z")])
        ballet_github.label_pull_request("43", "APPROVED", run=gh)
        edits = [call for call in gh.calls if call[:2] == ["pr", "edit"]]
        self.assertEqual(edits[0], ["pr", "edit", "43", "--remove-label", "ballet:approved"])
        self.assertEqual(edits[1][3:5], ["--add-label", "ballet:approved"])

    def test_label_refuse_un_verdict_inconnu(self):
        with self.assertRaisesRegex(ballet_github.GitHubError, "unknown verdict"):
            ballet_github.label_pull_request("43", "maybe", run=FakeGh())

    def test_la_decision_du_director_et_ses_commentaires_depuis_l_escalade(self):
        timeline = [labeled("ballet:escalated", "2026-11-16T10:30:00Z"), labeled("ballet:rejected", "2026-11-16T11:30:00Z")]
        decision = ballet_github.director_decision("43", run=FakeGh(timeline=timeline))
        self.assertEqual((decision["verdict"], decision["labeled_at"]), ("REJECTED", "2026-11-16T11:30:00Z"))
        self.assertEqual(decision["comments"], ["Dancer report, round 2"])

    def test_sans_escalade_pas_de_commentaire_du_director(self):
        self.assertEqual(ballet_github.director_decision("43", run=FakeGh(timeline=APPROVED_TIMELINE))["comments"], [])

    def assert_merge_refused(self, pull_request, reason, timeline=APPROVED_TIMELINE):
        gh, git = FakeGh(pull_request=pull_request, timeline=timeline), FakeGit()
        with self.assertRaisesRegex(ballet_github.GitHubError, reason):
            ballet_github.merge_pull_request("43", run=gh, git=git)
        self.assertFalse([call for call in gh.calls if call[:2] == ["pr", "merge"]])
        self.assertEqual(git.calls, [])

    def test_refuse_un_numero_invalide(self):
        with self.assertRaises(ballet_github.GitHubError):
            ballet_github.read_issue("abc", run=FakeGh())

    def test_refuse_une_operation_inconnue(self):
        self.assertEqual(ballet_github.main(["x", "delete", "7"]), 1)


def critic_review(review_id, round_, verdict, blocking, at):
    header = json.dumps({"ballet": "message", "from": "critic", "to": "conductor", "type": "verdict", "subject": "#2", "round": round_})
    points = "".join(f"{n}. `a.rs:{n}` (inline comment)\n" for n in range(1, blocking + 1))
    return {"id": review_id, "user": {"login": "b"}, "submitted_at": at, "html_url": f"https://github.com/o/r/pull/43#pullrequestreview-{review_id}",
            "body": f"{header}\n\nVERDICT: {verdict}\n\n## Blocking\n\n{points}"}


def thread(thread_id, review_id, body, path="a.rs", line=1, resolved=False):
    return {"id": thread_id, "isResolved": resolved,
            "comments": {"nodes": [{"body": body, "path": path, "line": line, "pullRequestReview": {"databaseId": review_id}}]}}


class FakeIssuesGh:
    """Des issues et leur état ; `issue list` rend ce que la recherche GitHub trouverait (floue)."""

    def __init__(self, issues):
        self.issues = issues
        self.calls = []

    def __call__(self, arguments):
        self.calls.append(arguments)
        if arguments[:2] == ["issue", "view"]:
            return json.dumps(self.issues[arguments[2]])
        if arguments[:2] == ["issue", "list"]:
            return json.dumps([{"number": int(n), "body": i["body"]} for n, i in self.issues.items() if i["state"] == "OPEN"])
        if arguments[:2] == ["issue", "close"]:
            self.issues[arguments[2]]["state"] = "CLOSED"
        return ""

    def closed(self):
        return [call[2] for call in self.calls if call[:2] == ["issue", "close"]]


def an_issue(body, state="OPEN"):
    return {"state": state, "body": body}


class CloseIssueTest(unittest.TestCase):
    def test_ferme_l_issue_livree_avec_un_renvoi_a_sa_pr(self):
        gh = FakeIssuesGh({"7": an_issue("## Context\n")})
        self.assertEqual(ballet_github.close_issue("#7", "#9", run=gh), ["7"])
        close = gh.calls[-1]
        self.assertEqual(close[:5], ["issue", "close", "7", "--reason", "completed"])
        self.assertIn("Done in #9.", close)

    def test_une_issue_deja_fermee_par_github_n_est_pas_refermee(self):
        gh = FakeIssuesGh({"7": an_issue("## Context\n", "CLOSED")})
        self.assertEqual(ballet_github.close_issue("7", "9", run=gh), [])
        self.assertEqual(gh.closed(), [])

    def test_la_derniere_slice_ferme_sa_parente(self):
        gh = FakeIssuesGh({"1": an_issue("## Context\n"), "6": an_issue("Part of #1\n\n## Context\n"),
                           "5": an_issue("Part of #1\n\n## Context\n", "CLOSED")})
        self.assertEqual(ballet_github.close_issue("6", "12", run=gh), ["6", "1"])

    def test_la_parente_reste_ouverte_tant_qu_une_slice_l_est(self):
        gh = FakeIssuesGh({"1": an_issue("## Context\n"), "4": an_issue("Part of #1\n\n## Context\n"),
                           "5": an_issue("Part of #1\n\n## Context\n")})
        self.assertEqual(ballet_github.close_issue("4", "10", run=gh), ["4"])

    def test_une_issue_qui_cite_la_parente_sans_en_etre_une_slice_ne_compte_pas(self):
        gh = FakeIssuesGh({"1": an_issue("## Context\n"), "6": an_issue("Part of #1\n"),
                           "8": an_issue("## Context\n\nSee Part of #1 for the background.\n"),
                           "11": an_issue("Part of #12\n")})
        self.assertEqual(ballet_github.close_issue("6", "12", run=gh), ["6", "1"])

    def test_la_slice_fermee_encore_listee_ouverte_par_la_recherche_ne_bloque_pas_la_parente(self):
        gh = FakeIssuesGh({"1": an_issue("## Context\n"), "6": an_issue("Part of #1\n")})
        original = gh.__call__
        stale = lambda arguments: (json.dumps([{"number": 6, "body": "Part of #1\n"}])
                                   if arguments[:2] == ["issue", "list"] else original(arguments))
        self.assertEqual(ballet_github.close_issue("6", "12", run=stale), ["6", "1"])


class PlanTest(unittest.TestCase):
    def test_les_slices_d_une_parente_dans_l_ordre_de_creation(self):
        gh = FakeIssuesGh({"1": an_issue("## Context\n"), "16": an_issue("Part of #1\n"), "9": an_issue("Part of #1\n"),
                           "8": an_issue("See Part of #1\n"), "11": an_issue("Part of #12\n"),
                           "7": an_issue("Part of #1\n", "CLOSED")})
        self.assertEqual(ballet_github.slices_of("#1", run=gh), ["9", "16"])
        self.assertNotIn("--search", gh.calls[0])

    def test_une_issue_sans_slices_n_en_a_aucune(self):
        self.assertEqual(ballet_github.slices_of("1", run=FakeIssuesGh({"1": an_issue("## Plan\n")})), [])


class FakeThreadsGh:
    """gh pour le résumé des verdicts et les fils de review."""

    def __init__(self, reviews, threads=(), comments=()):
        self.reviews, self.threads, self.comments = list(reviews), list(threads), list(comments)
        self.calls = []

    def __call__(self, arguments):
        self.calls.append(arguments)
        if arguments[0] == "api" and arguments[1] == "graphql":
            query = next(a for a in arguments if a.startswith("query="))
            if "reviewThreads" in query:
                return json.dumps({"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": self.threads}}}}})
            return "{}"
        if arguments[0] == "api" and arguments[1].endswith("/reviews"):
            return json.dumps([self.reviews])
        if arguments[0] == "api" and arguments[1].endswith("/issues/43/comments") and "--method" not in arguments:
            return json.dumps([self.comments])
        return "{}"

    def mutations(self, name):
        return [a for a in self.calls if a[:2] == ["api", "graphql"] and any(name in x for x in a)]

    def field(self, call, name):
        return next(a.split("=", 1)[1] for a in call if a.startswith(f"{name}="))


class VerdictsAndThreadsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def report(self, body):
        path = Path(self._tmp.name) / "r.md"
        header = json.dumps({"ballet": "message", "from": "dancer", "to": "conductor", "type": "report", "subject": "#2", "round": 2})
        path.write_text(f"{header}\n\n{body}\n", encoding="utf-8")
        return path

    def test_cree_le_commentaire_des_verdicts_avec_une_ligne_par_tour(self):
        gh = FakeThreadsGh([critic_review(11, 1, "REJECTED", 2, "2026-11-16T10:00:00Z"), critic_review(12, 2, "APPROVED", 0, "2026-11-16T12:00:00Z")])
        ballet_github.update_verdicts("#43", run=gh)
        post = [c for c in gh.calls if "--method" in c and "POST" in c][0]
        self.assertEqual(post[1], "repos/{owner}/{repo}/issues/43/comments")
        body = gh.field(post, "body")
        self.assertIn(ballet_github.VERDICTS_MARKER, body)
        self.assertIn("| 1 | REJECTED | 2 |", body)
        self.assertIn("| 2 | APPROVED | 0 |", body)
        self.assertLess(body.index("| 1 |"), body.index("| 2 |"))
        self.assertIn("pullrequestreview-12", body)

    def test_reecrit_le_commentaire_des_verdicts_s_il_existe(self):
        gh = FakeThreadsGh([critic_review(11, 1, "REJECTED", 1, "2026-11-16T10:00:00Z")],
                           comments=[{"id": 77, "body": f"{ballet_github.VERDICTS_MARKER}\nold"}, {"id": 78, "body": "Dancer report"}])
        ballet_github.update_verdicts("43", run=gh)
        patch = [c for c in gh.calls if "PATCH" in c][0]
        self.assertEqual(patch[1], "repos/{owner}/{repo}/issues/comments/77")
        self.assertFalse([c for c in gh.calls if "POST" in c])

    def test_ignore_les_reviews_qui_ne_sont_pas_des_verdicts(self):
        human = {"id": 13, "user": {"login": "b"}, "submitted_at": "2026-11-16T11:00:00Z", "html_url": "u", "body": "LGTM"}
        gh = FakeThreadsGh([critic_review(11, 1, "REJECTED", 1, "2026-11-16T10:00:00Z"), human])
        ballet_github.update_verdicts("43", run=gh)
        body = gh.field([c for c in gh.calls if "POST" in c][0], "body")
        self.assertEqual(body.count("\n| "), 2)  # en-tête du tableau + un tour

    def test_resout_les_fils_que_le_dancer_dit_corriges_avec_le_commit(self):
        gh = FakeThreadsGh(
            [critic_review(11, 1, "REJECTED", 2, "2026-11-16T10:00:00Z")],
            threads=[thread("T1", 11, "**Blocking 1** — Unused."), thread("T2", 11, "**Blocking 2** — Wrong."),
                     thread("T3", 11, "**Note** — Wide.", path="v.ts", line=11)])
        report = self.report("- Outcome: done\n\n## Fixed\n\n- Blocking 1: abc1234\n- Note `v.ts:11`: def5678\n- Blocking 9: 0000000\n")
        resolved, unmatched = ballet_github.resolve_fixed("43", report, run=gh)
        self.assertEqual(resolved, ["Blocking 1", "Note `v.ts:11`"])
        self.assertEqual(unmatched, ["Blocking 9"])
        replies = gh.mutations("addPullRequestReviewThreadReply")
        self.assertEqual([gh.field(c, "thread") for c in replies], ["T1", "T3"])
        self.assertIn("abc1234", gh.field(replies[0], "body"))
        self.assertEqual([gh.field(c, "thread") for c in gh.mutations("resolveReviewThread")], ["T1", "T3"])

    def test_resout_le_fil_d_une_note_dont_la_ligne_a_change_depuis_le_verdict(self):
        outdated = thread("T1", 11, "**Note** — Wide.", path="m.rs", line=None)
        outdated["comments"]["nodes"][0]["originalLine"] = 41
        gh = FakeThreadsGh([critic_review(11, 1, "APPROVED", 0, "2026-11-16T10:00:00Z")], threads=[outdated])
        resolved, unmatched = ballet_github.resolve_fixed("43", self.report("## Fixed\n\n- Note `m.rs:41`: abc1234\n"), run=gh)
        self.assertEqual((resolved, unmatched), (["Note `m.rs:41`"], []))

    def test_ne_touche_pas_un_fil_deja_resolu_ni_ceux_d_un_ancien_tour(self):
        gh = FakeThreadsGh(
            [critic_review(11, 1, "REJECTED", 1, "2026-11-16T10:00:00Z"), critic_review(12, 2, "REJECTED", 1, "2026-11-16T12:00:00Z")],
            threads=[thread("OLD", 11, "**Blocking 1** — Old."), thread("NEW", 12, "**Blocking 1** — New.", resolved=True)])
        resolved, _ = ballet_github.resolve_fixed("43", self.report("## Fixed\n\n- Blocking 1: abc1234\n"), run=gh)
        self.assertEqual(resolved, [])
        self.assertFalse(gh.mutations("resolveReviewThread"))

    def test_un_rapport_sans_section_fixed_ne_resout_rien(self):
        gh = FakeThreadsGh([critic_review(11, 1, "REJECTED", 1, "2026-11-16T10:00:00Z")], threads=[thread("T1", 11, "**Blocking 1** — x")])
        self.assertEqual(ballet_github.resolve_fixed("43", self.report("- Outcome: done"), run=gh), ([], []))


def stored_issue(number, title, body="", state="OPEN"):
    return {"number": number, "title": title, "body": body, "state": state}


class BalletGitHubDependenciesTest(unittest.TestCase):
    """Les dépendances entre éléments : les liens « Blocked by » de GitHub, posés à la publication ou à la main."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.specs = self.dir / "specs"
        (self.specs / "features").mkdir(parents=True)
        self.gh = FakeGh()

    def draft(self, title, depends=None):
        line = f"- **Depends on**: {depends}\n" if depends else ""
        path = self.dir / "draft.md"
        path.write_text(f"# {title}\n\n- **Type**: feature\n{line}\n## Context\n\nWhy.\n", encoding="utf-8")
        return path

    def publish(self, title, depends=None, issue_type="Feature"):
        return ballet_github.publish_issue_with_links(self.draft(title, depends), issue_type, "ready", run=self.gh, specs=self.specs)

    def test_la_publication_pose_un_lien_vers_l_issue_de_chaque_dependance_publiee(self):
        self.gh.issues = [stored_issue(7, "FEAT-002 · Cart"), stored_issue(8, "BUG-004 · Stock", state="CLOSED")]
        number, notes = self.publish("FEAT-003 · Pay", "FEAT-002, BUG-004")
        self.assertEqual((number, self.gh.links), ("42", [("42", "7"), ("42", "8")]))
        self.assertEqual(notes, ["#42 is now blocked by #7 (FEAT-002)", "#42 is now blocked by #8 (BUG-004)"])

    def test_lit_la_ligne_depends_on_sans_mise_en_forme_et_sans_doublon(self):
        self.gh.issues = [stored_issue(7, "FEAT-002 · Cart")]
        path = self.dir / "plain.md"
        path.write_text("# FEAT-003 · Pay\n\nDepends on: FEAT-002, FEAT-002 (the cart)\n\n## Context\n\nWhy.\n", encoding="utf-8")
        ballet_github.publish_issue(path, "Feature", "ready", run=self.gh, specs=self.specs)
        self.assertEqual(self.gh.links, [("42", "7")])

    def test_une_dependance_pas_encore_publiee_mais_ecrite_dans_les_specs_est_notee_sans_lien(self):
        (self.specs / "features" / "FEAT-002-cart.md").write_text("# FEAT-002 — Cart\n", encoding="utf-8")
        number, notes = self.publish("FEAT-003 · Pay", "FEAT-002")
        self.assertEqual((number, self.gh.links), ("42", []))
        self.assertEqual(notes, ["FEAT-002 is not published yet: #42 will be linked to it when it is"])

    def test_une_ligne_du_backlog_suffit_a_connaitre_une_dependance(self):
        (self.specs / "backlog.md").write_text("## Next up\n\n1. **BUG-004** · Stock goes negative\n", encoding="utf-8")
        self.assertEqual(self.publish("FEAT-003 · Pay", "BUG-004")[1], ["BUG-004 is not published yet: #42 will be linked to it when it is"])

    def test_quand_la_dependance_est_publiee_les_issues_ouvertes_qui_la_citent_lui_sont_liees(self):
        self.gh.issues = [stored_issue(9, "FEAT-003 · Pay", "- **Depends on**: FEAT-002\n"),
                          stored_issue(10, "FEAT-004 · Ship", "- **Depends on**: FEAT-002, FEAT-003\n"),
                          stored_issue(11, "FEAT-005 · Old", "Depends on: FEAT-002", state="CLOSED"),
                          stored_issue(12, "FEAT-006 · Other", "Depends on: FEAT-009\n")]
        number, notes = self.publish("FEAT-002 · Cart")
        self.assertEqual(self.gh.links, [("9", "42"), ("10", "42")])
        self.assertEqual(notes, ["#9 is now blocked by #42 (FEAT-002)", "#10 is now blocked by #42 (FEAT-002)"])

    def test_une_dependance_inconnue_refuse_la_publication_sans_rien_creer(self):
        self.gh.issues = [stored_issue(7, "FEAT-002 · Cart")]
        with self.assertRaisesRegex(ballet_github.GitHubError, "unknown dependency FEAT-099"):
            self.publish("FEAT-003 · Pay", "FEAT-002, FEAT-099")
        self.assertEqual([call for call in self.gh.calls if call[:2] == ["issue", "create"]], [])

    def test_un_element_ne_peut_pas_dependre_de_lui_meme(self):
        with self.assertRaisesRegex(ballet_github.GitHubError, "FEAT-003 cannot depend on itself"):
            self.publish("FEAT-003 · Pay", "FEAT-003")
        self.assertEqual([call for call in self.gh.calls if call[:2] == ["issue", "create"]], [])

    def test_un_brouillon_sans_identifiant_ni_dependance_ne_lit_pas_les_issues(self):
        self.publish("A request with no id")
        self.assertEqual([call for call in self.gh.calls if call[:2] == ["issue", "list"]], [])

    def test_un_brouillon_sans_dependance_ne_pose_aucun_lien(self):
        self.gh.issues = [stored_issue(7, "FEAT-002 · Cart")]
        self.assertEqual(self.publish("FEAT-003 · Pay"), ("42", []))
        self.assertEqual(self.gh.links, [])

    def test_un_lien_qui_echoue_ne_defait_pas_l_issue_creee_et_dit_comment_le_poser(self):
        self.gh.issues = [stored_issue(7, "FEAT-002 · Cart")]
        self.gh.link_failure = "Resource not accessible"
        number, notes = self.publish("FEAT-003 · Pay", "FEAT-002")
        self.assertEqual(number, "42")
        self.assertRegex(notes[0], r"could not link #42 to #7 \(FEAT-002\): Resource not accessible; retry with `block 42 --by 7`")

    def test_une_dependance_en_double_prend_l_issue_la_plus_ancienne(self):
        self.gh.issues = [stored_issue(20, "FEAT-002 · Cart again"), stored_issue(7, "FEAT-002 · Cart")]
        self.publish("FEAT-003 · Pay", "FEAT-002")
        self.assertEqual(self.gh.links, [("42", "7")])

    # --- block et unblock ---

    def test_block_pose_le_lien_blocked_by(self):
        self.assertEqual(ballet_github.block_issue("5", "#3", run=self.gh), "#5 is now blocked by #3")
        self.assertEqual(self.gh.links, [("5", "3")])

    def test_block_ne_repose_pas_un_lien_deja_la(self):
        self.gh.blocked_by = {"5": ["3"]}
        self.assertEqual(ballet_github.block_issue("5", "3", run=self.gh), "#5 is already blocked by #3")
        self.assertEqual(self.gh.links, [])

    def test_block_refuse_une_issue_bloquee_par_elle_meme_et_un_cycle_direct(self):
        with self.assertRaisesRegex(ballet_github.GitHubError, "cannot be blocked by itself"):
            ballet_github.block_issue("5", "5", run=self.gh)
        self.gh.blocked_by = {"3": ["5"]}
        with self.assertRaisesRegex(ballet_github.GitHubError, "#3 is already blocked by #5: that would make a dependency cycle"):
            ballet_github.block_issue("5", "3", run=self.gh)
        self.assertEqual(self.gh.links, [])

    def test_block_refuse_une_issue_inconnue(self):
        self.gh.missing = {"99"}
        with self.assertRaisesRegex(ballet_github.GitHubError, "issue #99 not found"):
            ballet_github.block_issue("5", "99", run=self.gh)

    def test_unblock_retire_le_lien(self):
        self.gh.blocked_by = {"5": ["3"]}
        self.assertEqual(ballet_github.unblock_issue("5", "3", run=self.gh), "#5 is no longer blocked by #3")
        self.assertEqual(self.gh.links, [("5", "3", "-")])

    def test_unblock_d_un_lien_absent_ne_change_rien(self):
        self.assertEqual(ballet_github.unblock_issue("5", "3", run=self.gh), "#5 was not blocked by #3")
        self.assertEqual(self.gh.links, [])

    def test_block_en_ligne_de_commande_veut_by(self):
        with self.assertRaisesRegex(ballet_github.GitHubError, "usage: block|unblock <issue> --by <issue>"):
            ballet_github._dispatch("block", ["5", "3", "4"])

    def test_la_requete_de_lecture_demande_les_deux_issues_et_leurs_bloqueurs(self):
        ballet_github.block_issue("5", "3", run=self.gh)
        query = next(argument for call in self.gh.calls for argument in call if "blocker: issue" in argument)
        self.assertIn("blockedBy(first: 100)", query)
        mutation = next(argument for call in self.gh.calls for argument in call if "addBlockedBy" in argument)
        self.assertIn("issueId: $issue, blockingIssueId: $blocker", mutation)


if __name__ == "__main__":
    unittest.main()
