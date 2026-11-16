import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ballet_size  # noqa: E402

NUMSTAT = "120\t30\tsrc/inventory.rs\n3\t1\tCargo.lock\n40\t0\tapps/web/yarn.lock\n-\t-\tdocs/logo.png\n"


class BalletSizeTest(unittest.TestCase):
    def test_compte_les_lignes_ajoutees_et_supprimees(self):
        self.assertEqual(ballet_size.measure(NUMSTAT, []).counted, 194)

    def test_un_binaire_compte_pour_zero(self):
        self.assertEqual(ballet_size.measure("-\t-\tlogo.png\n", []).counted, 0)

    def test_les_exclusions_traversent_les_dossiers(self):
        size = ballet_size.measure(NUMSTAT, ["*.lock"])
        self.assertEqual((size.counted, size.excluded), (150, 44))
        self.assertEqual(size.excluded_files, ["Cargo.lock", "apps/web/yarn.lock"])

    def test_au_dela_du_seuil_seulement(self):
        size = ballet_size.measure("100\t0\ta.rs\n", [])
        self.assertEqual((size.over(100), size.over(99)), (False, True))

    def test_mesure_la_branche_depuis_son_ancetre_commun_avec_main(self):
        calls = []
        ballet_size.branch_size("rehearsal/FEAT-001.2", [], lambda arguments: calls.append(arguments) or "")
        self.assertEqual(calls, [["diff", "--numstat", "origin/main...rehearsal/FEAT-001.2"]])


if __name__ == "__main__":
    unittest.main()
