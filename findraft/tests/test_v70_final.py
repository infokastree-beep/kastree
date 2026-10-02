"""Final items from the real-ledger review: versioned packs, one compliance
statement, canonical note line lists, nested predicate checks, leaf-level prior."""
import json
import pathlib
import tempfile
import unittest
from decimal import Decimal as D

from engine.mapping import aggregate
from engine.notes import build_note_context
from engine.pack import load_manifest, pack_dir
from engine.statements import CONSUMED_LINES, build_income_statement, build_sofp, prior_from_mapped
from tests.fixtures import MAPPINGS, tb_lines

CONTENT = pathlib.Path(__file__).resolve().parent.parent / "content"
PACK = CONTENT / "frs102-1a-ie" / "2024.09"
NOTES = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (PACK / "notes").glob("*.json")}


class TestVersionedPacks(unittest.TestCase):
    def test_pinned_version_resolves(self):
        self.assertEqual(pack_dir("frs102-1a-ie", "2024.09"), PACK)

    def test_unknown_version_and_bad_identity_refused(self):
        with self.assertRaises(FileNotFoundError):
            pack_dir("frs102-1a-ie", "2099.01")
        with self.assertRaises(ValueError):
            pack_dir("../frs102-1a-ie", "2024.09")

    def test_every_pack_manifest_matches_its_directory(self):
        for manifest in CONTENT.glob("*/*/pack.json"):
            with self.subTest(path=str(manifest)):
                load_manifest(manifest)

    def test_manifest_in_wrong_directory_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "frs102-1a-ie" / "2025.01" / "pack.json"
            p.parent.mkdir(parents=True)
            p.write_text((PACK / "pack.json").read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_manifest(p)


class TestComplianceStatements(unittest.TestCase):
    """Corrected in v7.4 against the licensed text: two DIFFERENT statements are
    required — 1A.6A on the SoFP (s.324(4A) CA 2014) and 1AD.3 in the notes (N1)."""

    def test_sofp_statement_and_n1_statement_both_present_once(self):
        s = build_sofp(aggregate(tb_lines(), MAPPINGS), {})
        self.assertIn("small companies regime", s["compliance_statement"])
        hits = [c for c, t in NOTES.items() if "Statement of compliance" in json.dumps(t)]
        self.assertEqual(hits, ["N1_POLICIES"])


class TestNoteLineLists(unittest.TestCase):
    def test_debtor_and_creditor_notes_list_real_presented_lines(self):
        n3 = set(NOTES["N3_DEBTORS"]["tableSpec"]["lines_from"])
        n4 = set(NOTES["N4_CREDITORS"]["tableSpec"]["lines_from"])
        self.assertLessEqual(n3 | n4, CONSUMED_LINES)
        self.assertEqual(n4, {"TRADE_CREDITORS", "OTHER_CREDITORS", "ACCRUALS", "CORP_TAX",
                              "VAT_CREDITOR", "PAYE_PRSI_CREDITOR", "DEFERRED_INCOME",
                              "BANK_OVERDRAFT", "LOANS_LT1Y", "LEASE_LIABILITY_LT1Y"})
        self.assertEqual(n3, {"TRADE_DEBTORS", "OTHER_DEBTORS", "PREPAYMENTS", "VAT_ASSET",
                              "PAYE_ASSET", "ACCRUED_INCOME", "DEFERRED_TAX_ASSET"})

    def test_typo_in_nested_condition_raises(self):
        bad = {"NX": {"includeWhen": "always",
                      "tableSpec": {"analysis": {"includeWhen": "SECURED_CREDITORZ != 0"}}}}
        with self.assertRaises(KeyError):
            build_note_context(aggregate(tb_lines(), MAPPINGS), bad)


class TestLeafLevelPrior(unittest.TestCase):
    def test_comparatives_render_by_the_same_code_as_current(self):
        m = aggregate(tb_lines(), MAPPINGS)
        prior = prior_from_mapped(m)
        for builder in (build_sofp, build_income_statement):
            for label, cur, prev in builder(m, prior)["rows"]:
                with self.subTest(line=label):
                    self.assertEqual(prev, cur)

    def test_chart_v2_lines_get_comparatives(self):
        prior_mapped = {"CASH": D("30000"), "SHARE_PREMIUM": D("-5000"),
                        "PROVISIONS": D("-2000"), "SHARE_CAPITAL": D("-100"),
                        "RETAINED_EARNINGS": D("-22900")}
        prior = prior_from_mapped(prior_mapped)
        rows = {label: prev for label, _, prev in build_sofp(prior_mapped, prior)["rows"]}
        self.assertEqual(rows["Share premium account"], D("5000"))
        self.assertEqual(rows["Provisions for liabilities"], D("-2000"))


if __name__ == "__main__":
    unittest.main()
