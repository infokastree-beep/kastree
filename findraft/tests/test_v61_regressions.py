"""Regressions for the v6.0 verification findings."""
import json, pathlib, tempfile, unittest
from decimal import Decimal as Dec
from tests.fixtures import RULES, tb_lines, MAPPINGS
from engine.mapping import aggregate
from engine.notes import select_notes
from engine.predicates import evaluate
from engine.reconciliation import review_rules

PACK = pathlib.Path(__file__).resolve().parent.parent / "content" / "frs102-1a-ie" / "2024.09"


class TestFailClosed(unittest.TestCase):
    def test_typo_in_critical_rule_still_blocks(self):
        rules = json.loads((PACK / "review-rules.json").read_text(encoding="utf-8"))
        for r in rules["rules"]:
            if r["id"] == "R-DIV-001":
                r["when"] = r["when"].replace("opening_re", "opening_RE")
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "r.json"
            p.write_text(json.dumps(rules))
            m = aggregate(tb_lines(), MAPPINGS)
            m["DIVIDENDS"] = Dec("900000")
            hits = review_rules(m, {}, Dec("157650"), pack_path=p)
        self.assertIn(("R-DIV-001", "CRITICAL"), [(h.code, h.severity) for h in hits])


class TestIntangibleSigns(unittest.TestCase):
    def test_fully_amortised_intangible_does_not_trigger_dep_rule(self):
        x = {"FA_INTANGIBLE_COST": Dec("50000"), "FA_INTANGIBLE_AMORT": Dec("-50000"),
             "DEPRECIATION_CHARGE": Dec("0")}
        self.assertEqual(review_rules(x, {}, Dec("1000"), pack_path=RULES), [])


class TestPredicateErrorsAreUniform(unittest.TestCase):
    def test_deep_nesting_is_valueerror(self):
        for e in ["(" * 300 + "1" + ")" * 300, "- " * 4000 + "1"]:
            with self.subTest(n=len(e)):
                with self.assertRaises(ValueError):
                    evaluate(e, {})

    def test_note_selection_surfaces_valueerror(self):
        with self.assertRaises(ValueError):
            select_notes({"N": {"includeWhen": "(" * 300 + "1" + ")" * 300}}, {})


if __name__ == "__main__":
    unittest.main()
