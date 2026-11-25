import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_cost

WORKTREE = "/orca/workspaces/demo/rehearsal-FEAT-001"
PROJECT = "/work/demo"
WINDOW = (datetime(2026, 11, 19, 17, 0, tzinfo=timezone.utc), datetime(2026, 11, 19, 18, 0, tzinfo=timezone.utc))


def answer(id, model="claude-opus-5-5", at="2026-11-19T17:10:00.000Z", input=0, output=0, read=0, one_hour=0, five_minutes=0, speed="standard"):
    usage = {"input_tokens": input, "output_tokens": output, "cache_read_input_tokens": read,
             "cache_creation_input_tokens": one_hour + five_minutes, "speed": speed,
             "cache_creation": {"ephemeral_1h_input_tokens": one_hour, "ephemeral_5m_input_tokens": five_minutes}}
    return {"type": "assistant", "timestamp": at, "message": {"id": id, "model": model, "usage": usage, "content": []}}


def asking(text):
    return {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def command(name, args):
    return {"type": "user", "message": {"role": "user", "content": f"<command-message>{name}</command-message> "
                                        f"<command-name>/{name}</command-name> <command-args>{args}</command-args>"}}


class CostTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.projects = Path(self.directory.name)

    def journal(self, path, session, records):
        folder = self.projects / ballet_cost.re.sub(r"[^A-Za-z0-9]", "-", path)
        folder.mkdir(exist_ok=True)
        (folder / f"{session}.jsonl").write_text("\n".join(json.dumps(record) for record in records) + "\n")

    def cost(self, item="#1", window=WINDOW):
        return ballet_cost.of_work(WORKTREE, PROJECT, "ballet:rehearsal", item, window, projects=self.projects)

    def rows_by_role(self, cost):
        return {row["role"]: row for row in cost["rows"]}

    def test_le_dossier_d_un_journal_est_le_chemin_sans_ses_separateurs(self):
        self.assertEqual(ballet_cost._folder_of("/Users/me/.claude/worktrees/x_1", Path("/p")), Path("/p/-Users-me--claude-worktrees-x-1"))

    def test_un_worker_est_chiffre_par_son_role_et_son_modele_au_prix_de_l_api(self):
        self.journal(WORKTREE, "aaaa1111-0", [asking("You are the Ballet Dancer of Rehearsal FEAT-001"),
                                              answer("m1", "claude-sonnet-5-5", input=1000, output=2000, read=1_000_000, one_hour=100_000)])
        cost = self.cost()
        dancer = self.rows_by_role(cost)["Dancer"]
        self.assertEqual((dancer["model"], dancer["input"], dancer["output"], dancer["cache_read"], dancer["cache_write_1h"]),
                         ("claude-sonnet-5-5", 1000, 2000, 1_000_000, 100_000))
        # 1000 × 2 + 2000 × 10 + 1M × 0,10 + 100k × 4, par million
        self.assertAlmostEqual(dancer["usd"], 0.002 + 0.02 + 0.10 + 0.40)
        self.assertAlmostEqual(cost["total"]["usd"], dancer["usd"])

    def test_une_reponse_ecrite_sur_plusieurs_lignes_n_est_comptee_qu_une_fois_avec_son_dernier_usage(self):
        self.journal(WORKTREE, "aaaa1111-0", [asking("You are the Ballet Critic"), answer("m1", output=10), answer("m1", output=500),
                                              answer("m2", output=100)])
        self.assertEqual(self.rows_by_role(self.cost())["Critic"]["output"], 600)

    def test_les_caches_de_cinq_minutes_et_d_une_heure_ont_chacun_leur_prix(self):
        self.journal(WORKTREE, "aaaa1111-0", [asking("You are the Ballet Critic"), answer("m1", five_minutes=1_000_000, one_hour=1_000_000)])
        self.assertAlmostEqual(self.cost()["total"]["usd"], 5.0 + 8.0)

    def test_deux_sessions_d_un_meme_role_ne_font_qu_une_ligne_par_modele(self):
        self.journal(WORKTREE, "aaaa1111-0", [asking("You are the Ballet Dancer"), answer("m1", output=10)])
        self.journal(WORKTREE, "bbbb2222-0", [asking("You are the Ballet Dancer"), answer("m2", output=20)])
        rows = [row for row in self.cost()["rows"] if row["role"] == "Dancer"]
        self.assertEqual([row["output"] for row in rows], [30])

    def test_une_session_sans_role_est_nommee_par_son_identifiant(self):
        self.journal(WORKTREE, "cccc3333-0", [asking("hello"), answer("m1", output=10)])
        self.assertIn("session cccc3333", self.rows_by_role(self.cost()))

    def test_un_modele_sans_prix_est_signale_et_compte_zero_dollar(self):
        self.journal(WORKTREE, "aaaa1111-0", [asking("You are the Ballet Critic"), answer("m1", "claude-new-9", output=10)])
        cost = self.cost()
        self.assertEqual(cost["total"]["usd"], 0)
        self.assertEqual(cost["left_out"][-1], "model without a price, counted as $0: claude-new-9")

    def test_le_mode_rapide_double_le_prix_d_opus_et_haiku_a_un_tarif_pour_les_longs_prompts(self):
        fast = ballet_cost._dollars("claude-opus-5-5", {**dict.fromkeys(ballet_cost.KINDS, 0), "output": 1_000_000}, "fast")
        self.assertAlmostEqual(fast, 40.0)
        short = {**dict.fromkeys(ballet_cost.KINDS, 0), "input": 1_000_000}
        long = {**dict.fromkeys(ballet_cost.KINDS, 0), "input": 200_000}
        self.assertAlmostEqual(ballet_cost._dollars("claude-haiku-5-5", short, "standard"), 0.50)
        self.assertAlmostEqual(ballet_cost._dollars("claude-haiku-5-5", long, "standard"), 200_000 * 0.50 / 1_000_000)
        self.assertAlmostEqual(ballet_cost._dollars("claude-haiku-5-5", {**short, "input": 50_000}, "standard"), 50_000 * 0.10 / 1_000_000)

    def test_deux_rehearsals_qui_partagent_un_worktree_se_partagent_ses_sessions_par_fenetre(self):
        self.journal(WORKTREE, "aaaa1111-0", [asking("You are the Ballet Choreographer"), answer("m1", output=10),
                                              answer("m2", at="2026-11-19T17:40:00.000Z", output=20)])
        later = (datetime(2026, 11, 19, 17, 30, tzinfo=timezone.utc), datetime(2026, 11, 19, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(self.rows_by_role(self.cost(window=WINDOW))["Choreographer"]["output"], 30)
        self.assertEqual(self.rows_by_role(self.cost(window=later))["Choreographer"]["output"], 20)

    def test_les_sous_agents_d_un_worker_sont_comptes_avec_lui(self):
        self.journal(WORKTREE, "aaaa1111-0", [asking("You are the Ballet Dancer"), answer("m1", output=10)])
        folder = self.projects / ballet_cost.re.sub(r"[^A-Za-z0-9]", "-", WORKTREE) / "aaaa1111-0" / "subagents"
        folder.mkdir(parents=True)
        (folder / "agent-1.jsonl").write_text(json.dumps(answer("s1", output=5)) + "\n")
        self.assertEqual(self.rows_by_role(self.cost())["Dancer"]["output"], 15)

    def test_le_conductor_est_compte_sur_la_fenetre_quand_une_seule_session_porte_l_element(self):
        self.journal(WORKTREE, "aaaa1111-0", [asking("You are the Ballet Dancer"), answer("m1", output=10)])
        self.journal(PROJECT, "dddd4444-0", [command("ballet:rehearsal", "#1"), answer("c1", output=100),
                                             answer("c2", at="2026-11-19T17:30:00.000Z", output=200),
                                             answer("c3", at="2026-11-19T19:00:00.000Z", output=9000)])
        self.journal(PROJECT, "eeee5555-0", [command("ballet:rehearsal", "#2"), answer("o1", output=7)])
        cost = self.cost()
        self.assertEqual(self.rows_by_role(cost)["Conductor"]["output"], 300)
        self.assertEqual(cost["left_out"], [])

    def test_le_conductor_est_laisse_de_cote_sans_session_ou_avec_deux_sessions_actives_a_la_fois(self):
        self.journal(WORKTREE, "aaaa1111-0", [asking("You are the Ballet Dancer"), answer("m1", output=10)])
        self.assertIn("Conductor not counted: no session of /ballet:rehearsal #1", self.cost()["left_out"][0])
        self.journal(PROJECT, "dddd4444-0", [command("ballet:rehearsal", "#1"), answer("c1", output=100)])
        self.journal(PROJECT, "eeee5555-0", [command("ballet:rehearsal", "#1"), answer("c2", output=100)])
        cost = self.cost()
        self.assertNotIn("Conductor", self.rows_by_role(cost))
        self.assertIn("2 sessions", cost["left_out"][0])

    def test_un_workshop_cherche_son_conductor_par_sa_commande(self):
        self.journal(WORKTREE, "aaaa1111-0", [asking("You are the Ballet Dramaturg"), answer("m1", output=10)])
        self.journal(PROJECT, "dddd4444-0", [command("ballet:workshop", "--autopilot FEAT-009"), answer("c1", output=100)])
        cost = ballet_cost.of_work(WORKTREE, PROJECT, "ballet:workshop", "FEAT-009", WINDOW, projects=self.projects)
        self.assertEqual(self.rows_by_role(cost)["Conductor"]["output"], 100)

    def test_sans_aucun_journal_le_cout_est_absent_et_le_dit(self):
        cost = self.cost()
        self.assertEqual(list(cost), ["missing"])
        self.assertIn("no Claude Code journal activity for rehearsal-FEAT-001 in its time window", cost["missing"])
        self.assertTrue(ballet_cost.line_of(cost).startswith("cost: not available (no Claude Code journal activity"))

    def test_la_ligne_donne_le_total_en_tokens_et_en_dollars_puis_chaque_role(self):
        self.journal(WORKTREE, "aaaa1111-0", [asking("You are the Ballet Dancer"), answer("m1", "claude-sonnet-5-5", output=1_000_000, read=2_000_000)])
        self.journal(WORKTREE, "bbbb2222-0", [asking("You are the Ballet Critic"), answer("m2", output=100_000)])
        line = ballet_cost.line_of(self.cost())
        self.assertEqual(line, "cost ~$12.20 API equivalent (3.1M tokens, 2.0M from cache): Dancer $10.20, Critic $2.00; "
                               "Conductor not counted: no session of /ballet:rehearsal #1 in the project's journals")


if __name__ == "__main__":
    unittest.main()


def publish_call(id, at, command="python3 ../../scripts/ballet_github.py publish /tmp/d.md Feature ready"):
    return {"type": "assistant", "timestamp": at, "message": {"id": f"call-{id}", "model": "<synthetic>", "content": [
        {"type": "tool_use", "id": id, "name": "Bash", "input": {"command": command}}]}}


def tool_result(id, at, is_error=False):
    return {"type": "user", "timestamp": at, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": id, "content": "42", "is_error": is_error}]}}


HERE = "/work/demo"
NOW = datetime(2026, 11, 19, 19, 0, tzinfo=timezone.utc)


class SessionCostTest(unittest.TestCase):
    """Le coût de la session qui publie (OPP-95) : sa tranche depuis le `publish` précédent, et sa note dans l'issue."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.projects = Path(self.directory.name)

    def journal(self, records, session="sess-1", path=HERE):
        folder = self.projects / ballet_cost.re.sub(r"[^A-Za-z0-9]", "-", path)
        folder.mkdir(exist_ok=True)
        (folder / f"{session}.jsonl").write_text("\n".join(json.dumps(record) for record in records) + "\n")
        return folder

    def measure(self, session="sess-1"):
        return ballet_cost.of_this_session(cwd=HERE, session_id=session, projects=self.projects, now=NOW)

    def note(self, **changes):
        measure = self.measure()
        text = ballet_cost.render_cost_note(measure)
        payload = json.loads(ballet_cost.COST_NOTE.search(text).group(1))
        payload.update(changes)
        return f"line\n\n<!-- ballet:cost\n{json.dumps(payload)}\n-->"

    def test_sans_publish_precedent_la_tranche_est_toute_la_session(self):
        self.journal([answer("m1", at="2026-11-19T17:10:00Z", output=10), answer("m2", at="2026-11-19T17:20:00Z", output=5)])
        measure = self.measure()
        self.assertEqual((measure["segment"], measure["segment_total"]["output"], measure["session_total"]["output"]), (1, 15, 15))
        self.assertEqual(measure["from"], datetime(2026, 11, 19, 17, 10, tzinfo=timezone.utc))

    def test_deux_publish_coupent_la_session_en_tranches(self):
        self.journal([answer("m1", at="2026-11-19T17:10:00Z", output=10), publish_call("t1", "2026-11-19T17:30:00Z"),
                      tool_result("t1", "2026-11-19T17:30:05Z"), answer("m2", at="2026-11-19T17:40:00Z", output=7),
                      publish_call("t2", "2026-11-19T17:50:00Z")])   # l'appel en cours : pas encore de résultat
        measure = self.measure()
        self.assertEqual((measure["segment"], measure["segment_total"]["output"], measure["session_total"]["output"]), (2, 7, 17))
        self.assertEqual(measure["from"], datetime(2026, 11, 19, 17, 30, 5, tzinfo=timezone.utc))

    def test_un_publish_refuse_ne_coupe_pas_la_tranche(self):
        self.journal([answer("m1", at="2026-11-19T17:10:00Z", output=10), publish_call("t1", "2026-11-19T17:30:00Z"),
                      tool_result("t1", "2026-11-19T17:30:05Z", is_error=True), answer("m2", at="2026-11-19T17:40:00Z", output=7)])
        self.assertEqual((self.measure()["segment"], self.measure()["segment_total"]["output"]), (1, 17))

    def test_les_sous_agents_de_la_session_sont_comptes(self):
        folder = self.journal([answer("m1", output=10)])
        (folder / "sess-1" / "subagents").mkdir(parents=True)
        (folder / "sess-1" / "subagents" / "agent-1.jsonl").write_text(json.dumps(answer("s1", output=4)) + "\n")
        self.assertEqual(self.measure()["segment_total"]["output"], 14)

    def test_la_session_est_trouvee_meme_lancee_depuis_un_autre_dossier(self):
        self.journal([answer("m1", output=3)], path="/elsewhere")
        self.assertEqual(self.measure()["session"], "sess-1")

    def test_un_journal_introuvable_le_dit(self):
        self.assertIn("missing", self.measure("unknown"))

    def test_la_note_se_relit_telle_quelle(self):
        self.journal([answer("m1", output=1000, read=200_000)])
        text = ballet_cost.render_cost_note(self.measure())
        self.assertIn("**Assisted Workshop cost** · this issue:", text)
        note = ballet_cost.parse_cost_note(text)
        self.assertEqual((note["v"], note["kind"], note["session"], note["segment"]), (1, "workshop-assisted", "sess-1", 1))
        self.assertEqual(note["tokens"]["claude-opus-5-5"]["cache_read"], 200_000)
        self.assertIsNone(ballet_cost.cost_note_problem(text))

    def test_un_bloc_tronque_est_illisible_sans_lever(self):
        self.journal([answer("m1", output=10)])
        truncated = ballet_cost.render_cost_note(self.measure())[:-30] + "-->"
        self.assertIsNone(ballet_cost.parse_cost_note(truncated))
        self.assertEqual(ballet_cost.cost_note_problem(truncated), "malformed")

    def test_un_champ_du_mauvais_type_est_illisible(self):
        self.journal([answer("m1", output=10)])
        for changes in ({"usd": "0.5"}, {"segment": 0}, {"segment": True}, {"session": ""}, {"from": "hier"},
                        {"tokens": {"claude-opus-5-5": {"input": -1}}}, {"kind": "rehearsal"}, {"kind": "workshop"}):
            with self.subTest(changes=changes):
                self.assertIsNone(ballet_cost.parse_cost_note(self.note(**changes)))
                self.assertEqual(ballet_cost.cost_note_problem(self.note(**changes)), "malformed")

    def test_un_champ_manquant_est_illisible(self):
        self.journal([answer("m1", output=10)])
        text = self.note()
        payload = json.loads(ballet_cost.COST_NOTE.search(text).group(1))
        del payload["to"]
        self.assertIsNone(ballet_cost.parse_cost_note(f"<!-- ballet:cost {json.dumps(payload)} -->"))

    def test_une_version_inconnue_est_dite_par_son_numero(self):
        self.journal([answer("m1", output=10)])
        self.assertIsNone(ballet_cost.parse_cost_note(self.note(v=2)))
        self.assertEqual(ballet_cost.cost_note_problem(self.note(v=2)), "format v2")

    def test_un_texte_sans_note_n_a_ni_note_ni_probleme(self):
        for text in ("a plain comment", "", None, 42):
            self.assertIsNone(ballet_cost.parse_cost_note(text))
            self.assertIsNone(ballet_cost.cost_note_problem(text))
