"""Regression tests for findings in the v5.5 code review."""
import json, pathlib, tempfile, unittest
from decimal import Decimal as Dec
from tests.fixtures import RULES, tb_lines, MAPPINGS, PRIOR
from engine.mapping import aggregate
from engine.money import D
from engine.notes import build_note_context
from engine.predicates import evaluate
from engine.reconciliation import (check_bs_balances, check_comparatives,
                                   check_prior_year_gate, review_rules)
from engine.rounding import flag_for_note
from engine.schemas import TBLine
from engine.statements import build_income_statement, build_sofp


def mapped():
    return aggregate(tb_lines(), MAPPINGS)


class TestStatementsNeverDropMoney(unittest.TestCase):
    def test_unpresented_line_raises(self):
        m = mapped(); m["ADMIN_EXPENSES_RENT"] = Dec("5000")
        with self.assertRaises(ValueError):
            build_sofp(m, PRIOR)

    def test_other_operating_income_balances(self):
        m = mapped(); m["OTHER_OPERATING_INCOME"] = Dec("-5000"); m["CASH"] += Dec("5000")
        self.assertTrue(check_bs_balances(build_sofp(m, PRIOR)).passed)

    def test_lease_liability_in_net_assets(self):
        m = mapped(); m["ROU_ASSETS"] = Dec("9000")
        m["LEASE_LIABILITY_LT1Y"] = Dec("-2000"); m["LEASE_LIABILITY_GT1Y"] = Dec("-7000")
        s = build_sofp(m, PRIOR)
        self.assertTrue(check_bs_balances(s).passed)
        self.assertEqual(s["net_assets"], Dec("455812.00"))

    def test_income_statement_comparatives_signed_and_articulate(self):
        rows = {l: p for l, _, p in build_income_statement(mapped(), PRIOR)["rows"]}
        self.assertEqual(rows["Cost of sales"], Dec("-1402000"))
        self.assertEqual(rows["Administrative expenses (including depreciation)"], Dec("-560300"))
        self.assertEqual(rows["Gross profit"] + rows["Administrative expenses (including depreciation)"],
                         rows["Operating profit"])


    def test_intangibles_presented_separately(self):
        m = mapped()
        m["FA_INTANGIBLE_COST"] = Dec("30000")
        m["FA_INTANGIBLE_AMORT"] = Dec("-5000")
        m["RETAINED_EARNINGS"] = m["RETAINED_EARNINGS"] - Dec("25000")
        s = build_sofp(m, PRIOR)
        rows = {l: c for l, c, _ in s["rows"]}
        self.assertEqual(rows["Intangible assets"], Dec("25000"))
        self.assertEqual(rows["Tangible assets"], Dec("134000.00"))
        self.assertTrue(check_bs_balances(s).passed)


class TestGateAndComparatives(unittest.TestCase):
    def test_gate_blocks(self):
        self.assertEqual(check_prior_year_gate(False).severity, "BLOCKED")
        self.assertIsNone(check_prior_year_gate(True))

    def test_missing_comparative_flagged(self):
        self.assertEqual([r.code for r in check_comparatives({"NEW": Dec("5")}, {})], ["V-CMP-002"])


class TestReviewRules(unittest.TestCase):
    def test_dividend_from_brought_forward_reserves_is_lawful(self):
        m = mapped()
        self.assertEqual(review_rules(m, {}, profit_for_year=Dec("-10000"), pack_path=RULES), [])

    def test_dividend_exceeding_reserves_is_critical(self):
        m = mapped(); m["DIVIDENDS"] = Dec("500000")
        hits = review_rules(m, {}, profit_for_year=Dec("157650"), pack_path=RULES)
        self.assertEqual([(h.code, h.severity) for h in hits], [("R-DIV-001", "CRITICAL")])

    def test_broken_pack_rule_becomes_error_not_crash(self):
        import tempfile, pathlib as pl, json as js
        with tempfile.TemporaryDirectory() as d:
            p = pl.Path(d) / "r.json"
            p.write_text(js.dumps({"rules": [{"id": "X", "scope": "client",
                "severity": "INFO", "when": "balance/0 > 1", "message": "m"}]}))
            hits = review_rules(mapped(), {}, Dec("1"), pack_path=p)
        self.assertEqual([(h.code, h.severity) for h in hits], [("X", "CRITICAL")])

    def test_message_template_cannot_walk_attributes(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "r.json"
            p.write_text(json.dumps({"rules": [{"id": "X", "scope": "client", "severity": "INFO",
                                                "when": "True", "message": "{dividends.__class__}"}]}))
            msg = review_rules(mapped(), {}, Dec("1"), pack_path=p)[0].message
        self.assertNotIn("decimal", msg)


class TestPredicates(unittest.TestCase):
    def test_short_circuit(self):
        self.assertFalse(evaluate("x != 0 and 10 / x > 1", {"x": 0}))

    def test_string_repetition_rejected(self):
        with self.assertRaises(ValueError):
            evaluate("'a' * 999999999999", {})

    def test_unsupported_comparison_is_valueerror(self):
        with self.assertRaises(ValueError):
            evaluate("x in y", {"x": 1, "y": [1]})


class TestInputHardening(unittest.TestCase):
    def test_tbline_rejects_float_and_negative(self):
        with self.assertRaises(TypeError):
            TBLine("1", "x", 0.1, Dec("0"))  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            TBLine("1", "x", Dec("-1"), Dec("0"))

    def test_money_rejects_non_finite_and_overflow(self):
        for bad in ("Infinity", "1e13"):
            with self.assertRaises(ValueError):
                D(bad)

    def test_intangibles_not_polluted_by_tangible_depreciation(self):
        self.assertEqual(build_note_context(mapped(), {})["INTANGIBLE_ASSETS"], Dec("0"))

    def test_deeplink_is_url_encoded(self):
        link = flag_for_note([Dec("1.4")], Dec("2"), 1, 'x"><script>')["deeplink"]
        self.assertNotIn("<", link)


if __name__ == "__main__":
    unittest.main()
