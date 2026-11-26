import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_planning  # noqa: E402

ALL_STATUS = ["proposed", "ready", "in-rehearsal", "plan-review", "escalated", "done"]


def owner(types=("Task", "Bug", "Feature"), fields=None, typename="User"):
    nodes = [{"name": name, "options": [{"name": option} for option in options]} for name, options in (fields or {}).items()]
    return json.dumps({"data": {"repositoryOwner": {
        "__typename": typename, "id": "U_owner", "login": "bdridi",
        "issueTypes": {"nodes": [{"name": name} for name in types]},
        "issueFields": {"nodes": nodes},
    }}})


class FakeGitHub:
    """Rejoue la lecture du propriétaire, accepte toute création et garde les mutations envoyées."""

    def __init__(self, owner_json, mutation_reply='{"data": {}}'):
        self.owner_json = owner_json
        self.mutation_reply = mutation_reply
        self.mutations = []

    def __call__(self, arguments):
        query = next(argument for argument in arguments if argument.startswith("query="))
        if query.startswith("query=query"):
            return self.owner_json
        self.mutations.append(query)
        return self.mutation_reply


class PrepareTest(unittest.TestCase):
    def test_un_compte_vierge_recoit_le_type_slice_et_les_trois_champs(self):
        github = FakeGitHub(owner())
        report = ballet_planning.prepare(run=github)
        self.assertEqual(report["created"], ["issue type Slice", "issue field Ballet status", "issue field Rehearsal mode",
                                             "issue field Size", "issue field Plan approval", "issue field Priority"])
        self.assertEqual(len(github.mutations), 6)

    def test_rien_n_est_cree_quand_tout_existe(self):
        fields = {"Ballet status": ALL_STATUS, "Rehearsal mode": ["assisted", "autopilot"], "Size": ["S", "M"],
                  "Plan approval": ["required", "skipped"], "Priority": ["Urgent", "High", "Medium", "Low"]}
        github = FakeGitHub(owner(types=("Task", "Bug", "Feature", "Slice"), fields=fields))
        report = ballet_planning.prepare(run=github)
        self.assertEqual(report["created"], [])
        self.assertEqual(github.mutations, [])
        self.assertEqual(report["incomplete"], [])

    def test_un_champ_existant_n_est_jamais_modifie_mais_ses_options_manquantes_sont_signalees(self):
        github = FakeGitHub(owner(fields={"Ballet status": ["ready", "done"]}))
        report = ballet_planning.prepare(run=github)
        self.assertIn("issue field Ballet status", report["kept"])
        self.assertEqual(report["incomplete"], [("issue field Ballet status", ["proposed", "in-rehearsal", "plan-review", "escalated"])])
        self.assertFalse(any("Ballet status" in mutation for mutation in github.mutations))

    def test_le_champ_size_a_les_options_s_et_m_dans_cet_ordre(self):
        github = FakeGitHub(owner())
        ballet_planning.prepare(run=github)
        size = next(mutation for mutation in github.mutations if '"Size"' in mutation)
        self.assertLess(size.index('"S"'), size.index('"M"'))
        self.assertNotIn('"L"', size)

    def test_un_type_par_defaut_absent_est_cree(self):
        github = FakeGitHub(owner(types=("Bug",)))
        report = ballet_planning.prepare(run=github)
        self.assertEqual([name for name in report["created"] if name.startswith("issue type")], ["issue type Task", "issue type Feature", "issue type Slice"])

    def test_les_options_partent_dans_l_ordre_avec_leur_couleur(self):
        github = FakeGitHub(owner())
        ballet_planning.prepare(run=github)
        status = next(mutation for mutation in github.mutations if '"Ballet status"' in mutation)
        self.assertIn('{name: "proposed", color: GRAY', status)
        self.assertIn('priority: 1}', status)
        self.assertLess(status.index('"ready"'), status.index('"done"'))
        self.assertIn('ownerId: "U_owner"', status)

    def test_une_organisation_se_prepare_comme_un_compte_personnel(self):
        report = ballet_planning.prepare(run=FakeGitHub(owner(typename="Organization")))
        self.assertIn("issue type Slice", report["created"])

    def test_un_refus_de_github_dit_quel_droit_manque(self):
        github = FakeGitHub(owner(), mutation_reply='{"errors": [{"message": "bdridi does not have the correct permissions to execute `CreateIssueType`"}]}')
        with self.assertRaises(ballet_planning.PlanningError) as raised:
            ballet_planning.prepare(run=github)
        self.assertIn("gh auth refresh -h github.com -s user", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
