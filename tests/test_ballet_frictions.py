import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_frictions


def entry(event, at="2026-11-21T21:00:00+00:00", **detail):
    return {"at": at, "rehearsal": "FEAT-007", "event": event, "detail": detail}


class FrictionsTest(unittest.TestCase):
    def test_une_rehearsal_sans_accroc_n_a_aucune_friction_et_garde_sa_duree(self):
        entries = [entry("begin"), entry("done", at="2026-11-21T21:42:00+00:00")]
        record = ballet_frictions.of_rehearsal({}, entries)
        self.assertEqual(record, {"seconds": 2520, "frictions": []})
        self.assertEqual(ballet_frictions.line("FEAT-007", record), "frictions of FEAT-007 (42 min): none")

    def test_chaque_accroc_devient_une_friction_lisible(self):
        state = {"round_trips": 2, "red_proofs": 1, "red_mutations": 0, "refused_reports": 1,
                 "violations": {"dancer": 1, "critic": 0}, "size": {"over": True, "counted": 1527, "limit": 1500}}
        entries = [entry("begin"), entry("escalate", reason="invalid message, send it back to its author: file not found: --help"),
                   entry("handoff", how="nudge"), entry("handoff", how="start")]
        texts = [friction["text"] for friction in ballet_frictions.of_rehearsal(state, entries)["frictions"]]
        self.assertEqual(texts, ["escalated: invalid message, send it back to its author: file not found: --help",
                                 "2 Critic rejections", "1 red proof", "1 Dancer report refused",
                                 "1 worker reminded to send its worker_done", "policy refused: dancer ×1",
                                 "diff 1527 lines over the 1500 limit"])

    def test_la_ligne_du_done_enchaine_les_frictions(self):
        record = {"seconds": 9000, "frictions": [{"kind": "red_proofs", "count": 1, "text": "1 red proof"},
                                                 {"kind": "diff", "count": 1, "text": "diff 1527 lines over the 1500 limit"}]}
        self.assertEqual(ballet_frictions.line("FEAT-007", record),
                         "frictions of FEAT-007 (2 h 30): 1 red proof; diff 1527 lines over the 1500 limit")

    def test_un_long_motif_d_escalade_est_raccourci(self):
        frictions = ballet_frictions.of_rehearsal({}, [entry("escalate", reason="x" * 500)])["frictions"]
        self.assertEqual(len(frictions[0]["text"]), len("escalated: ") + ballet_frictions.ESCALATION_TEXT_LIMIT)

    def test_un_workshop_compte_les_rapports_refuses_et_les_violations_du_dramaturg(self):
        record = ballet_frictions.of_workshop({"refused_reports": 2, "violations": 1}, [entry("begin")])
        self.assertEqual([friction["text"] for friction in record["frictions"]],
                         ["2 Dramaturg reports refused", "policy refused: dramaturg ×1"])

    def test_les_avis_idle_du_monitor_sont_comptes(self):
        entries = [entry("begin"), entry("idle", notice=1), entry("idle", notice=2), entry("handoff", how="nudge")]
        record = ballet_frictions.of_rehearsal({}, entries)
        idle = [friction for friction in record["frictions"] if friction["kind"] == "idle"]
        self.assertEqual(idle, [{"kind": "idle", "count": 2, "text": "silent 2 times: Monitor idle notices"}])
        self.assertEqual([friction["kind"] for friction in record["frictions"]], ["nudges", "idle"])

    def test_un_seul_avis_idle_est_au_singulier_et_aucun_n_est_muet(self):
        one = ballet_frictions.of_workshop({}, [entry("idle")])["frictions"]
        self.assertEqual([friction["text"] for friction in one], ["silent 1 time: Monitor idle notice"])
        self.assertEqual(ballet_frictions.of_workshop({}, [entry("begin")])["frictions"], [])


if __name__ == "__main__":
    unittest.main()
