import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_db  # noqa: E402
import ballet_workshop_costs  # noqa: E402

KINDS = ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read")


def note_body(session="sess-1", segment=1, usd=0.5, version=1):
    note = {"v": version, "kind": "workshop-assisted", "session": session, "segment": segment,
            "from": f"2026-11-25T0{segment}:00:00+00:00", "to": f"2026-11-25T0{segment}:30:00+00:00", "usd": usd,
            "tokens": {"claude-opus-5-5": dict.fromkeys(KINDS, 10)}}
    return f"**Assisted Workshop cost** · …\n\n<!-- ballet:cost\n{json.dumps(note)}\n-->"


def issue(number, updated, *bodies):
    return {"number": number, "title": f"FEAT-00{number} · Thing", "updatedAt": updated,
            "comments": {"nodes": [{"id": f"c{number}-{index}", "body": body} for index, body in enumerate(bodies)]}}


class FakeGitHub:
    """Les issues du repo ; rend celles mises à jour depuis `since`, dans l'ordre, par pages de `first`."""

    def __init__(self, issues):
        self.issues, self.calls = issues, []

    def __call__(self, arguments, home):
        self.calls.append(arguments)
        since = next(a for a in arguments if a.startswith("since=")).split("=", 1)[1]
        first = int(next(a for a in arguments if a.startswith("first=")).split("=", 1)[1])
        page = [x for x in sorted(self.issues, key=lambda x: x["updatedAt"]) if x["updatedAt"] >= since][:first]
        return json.dumps({"data": {"repository": {"issues": {"nodes": page}}}})


class WorkshopCostsTest(unittest.TestCase):
    """Les notes `ballet:cost` des Workshops assisted, lues par le Monitor et rangées dans la base (OPP-95)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        environment = mock.patch.dict("os.environ", {"BALLET_HOME": str(Path(self._tmp.name) / "ballet-home")})
        environment.start()
        self.addCleanup(environment.stop)

    def sweep(self, github, page_size=50):
        return ballet_workshop_costs.sweep("shop", self._tmp.name, run=github, page_size=page_size)

    def rows(self):
        with ballet_db.reading() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM workshop_costs ORDER BY session, segment")]

    def test_les_notes_sont_rangees_et_la_marque_avance(self):
        github = FakeGitHub([issue(7, "2026-11-25T10:00:00Z", "hello", note_body(segment=1)),
                             issue(8, "2026-11-25T11:00:00Z", note_body(segment=2, usd=0.25))])
        self.assertEqual(self.sweep(github), "shop: 2 issue(s) read, 2 cost note(s), 0 unreadable")
        self.assertEqual([(row["issue"], row["segment"], row["usd"]) for row in self.rows()], [(7, 1, 0.5), (8, 2, 0.25)])
        self.assertEqual(ballet_workshop_costs.watermark("shop"), "2026-11-25T11:00:00Z")

    def test_relire_les_memes_issues_ne_change_rien(self):
        github = FakeGitHub([issue(7, "2026-11-25T10:00:00Z", note_body())])
        self.sweep(github)
        self.sweep(github)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(ballet_workshop_costs.read()["sessions"][0]["usd"], 0.5)

    def test_le_tour_suivant_ne_relit_que_depuis_la_marque(self):
        github = FakeGitHub([issue(7, "2026-11-25T10:00:00Z", note_body())])
        self.sweep(github)
        github.issues.append(issue(9, "2026-11-25T12:00:00Z", note_body(session="sess-2")))
        self.sweep(github)
        self.assertIn("since=2026-11-25T10:00:00Z", github.calls[-1])
        self.assertEqual({row["session"] for row in self.rows()}, {"sess-1", "sess-2"})

    def test_un_gros_arriere_se_rattrape_page_par_page(self):
        github = FakeGitHub([issue(n, f"2026-11-25T1{n}:00:00Z", note_body(session=f"s{n}")) for n in range(1, 6)])
        self.sweep(github, page_size=2)
        self.assertEqual(len(self.rows()), 2)   # une page par tour, jamais tout l'arriéré d'un coup
        for _ in range(3):   # la marque est incluse : chaque page relit la dernière issue de la précédente, sans effet
            self.sweep(github, page_size=2)
        self.assertEqual(len(self.rows()), 5)

    def test_la_marque_n_avance_pas_si_la_page_n_est_pas_rangee(self):
        github = FakeGitHub([issue(7, "2026-11-25T10:00:00Z", note_body())])
        with mock.patch.object(ballet_workshop_costs.ballet_db, "writing", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.sweep(github)
        self.assertEqual(ballet_workshop_costs.watermark("shop"), ballet_workshop_costs.BEGINNING)

    def test_une_note_illisible_est_gardee_sans_arreter_le_passage(self):
        github = FakeGitHub([issue(7, "2026-11-25T10:00:00Z", note_body(version=2), "<!-- ballet:cost {oops -->"),
                             issue(8, "2026-11-25T11:00:00Z", note_body())])
        self.assertEqual(self.sweep(github), "shop: 2 issue(s) read, 1 cost note(s), 2 unreadable")
        read = ballet_workshop_costs.read()
        self.assertEqual([x["problem"] for x in read["unreadable"]], ["cost unreadable (format v2)", "cost unreadable (malformed)"])
        self.assertEqual(len(read["sessions"]), 1)
        self.sweep(github)
        self.assertEqual(len(ballet_workshop_costs.read()["unreadable"]), 2)

    def test_une_tranche_manquante_est_dite_inconnue_jamais_zero(self):
        self.sweep(FakeGitHub([issue(7, "2026-11-25T10:00:00Z", note_body(segment=1)),
                               issue(9, "2026-11-25T11:00:00Z", note_body(segment=3))]))
        [session] = ballet_workshop_costs.read()["sessions"]
        self.assertEqual((session["unknown"], session["usd"]), (["segment 2: cost unknown"], 1.0))

    def test_une_meme_tranche_sur_deux_issues_ne_compte_qu_une_fois(self):
        self.sweep(FakeGitHub([issue(7, "2026-11-25T10:00:00Z", note_body()), issue(8, "2026-11-25T11:00:00Z", note_body())]))
        [session] = ballet_workshop_costs.read()["sessions"]
        self.assertEqual((session["usd"], len(session["issues"])), (0.5, 1))

    def test_la_scene_ne_recoit_que_les_sessions_les_plus_recentes(self):
        self.sweep(FakeGitHub([issue(n, f"2026-11-25T1{n}:00:00Z", note_body(session=f"s{n}", segment=n)) for n in range(1, 4)]))
        self.assertEqual([s["session"] for s in ballet_workshop_costs.read(shown=2)["sessions"]], ["s3", "s2"])

    def test_un_github_qui_refuse_leve_une_erreur_du_tour_sans_bouger_la_marque(self):
        with self.assertRaisesRegex(ballet_workshop_costs.WorkshopCostError, "Bad credentials"):
            self.sweep(lambda arguments, home: json.dumps({"errors": [{"message": "Bad credentials"}]}))
        with self.assertRaisesRegex(ballet_workshop_costs.WorkshopCostError, "not JSON"):
            self.sweep(lambda arguments, home: "<html>")
        self.assertEqual(ballet_workshop_costs.watermark("shop"), ballet_workshop_costs.BEGINNING)

    def test_sans_issue_nouvelle_rien_ne_s_ecrit(self):
        self.assertEqual(self.sweep(FakeGitHub([])), f"shop: no issue updated since {ballet_workshop_costs.BEGINNING}")
