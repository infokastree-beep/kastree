"""Fail-closed behaviour required by the v7.4 independent review (Fire Drill 3).
Each test states the behaviour; none depends on a release number."""
import json
import pathlib
import random
import unittest
from decimal import Decimal as D

from engine.mapping import aggregate
from engine.notes import ANSWER_FLAGS, DERIVED, build_note_context, check_disclosure_answers, select_notes
from engine.pack import load_manifest, pin_pack_version
from engine.predicates import evaluate
from engine.reconciliation import check_bs_balances, check_tb_integrity, load_review_rules, review_rules
from engine.schemas import TBLine
from engine.statements import build_income_statement, build_sofp, prior_from_mapped
from tests.fixtures import RULES

PACK = pathlib.Path(__file__).resolve().parent.parent / "content" / "frs102-1a-ie" / "2024.09"
NOTES = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (PACK / "notes").glob("*.json")}
CHECKLIST = json.loads((PACK / "disclosure-checklist.json").read_text(encoding="utf-8"))["items"]
ALL_NO = {n: False for n in ANSWER_FLAGS}


def tb(bal: dict, names: dict | None = None):
    lines, maps = [], {}
    for i, (line, v) in enumerate(bal.items()):
        code, v = str(9000 + i), D(v)
        lines.append(TBLine(code, (names or {}).get(line, line.title()),
                            v if v > 0 else D("0"), -v if v < 0 else D("0")))
        maps[code] = line
    return lines, maps


FIXTURE_2 = {"CASH": "40000", "DIRECTOR_LOAN": "50000", "FA_FIXTURES_COST": "12000",
             "VAT_CONTROL": "-21500", "PAYE_PRSI": "-8300", "SHARE_CAPITAL": "-100",
             "RETAINED_EARNINGS": "-72100"}


class DisclosureAnswers(unittest.TestCase):
    def test_overdrawn_directors_loan_is_derived_and_triggers_its_disclosures(self):
        m = aggregate(*tb(FIXTURE_2))
        ctx = build_note_context(m, NOTES, ALL_NO)
        self.assertEqual(ctx["DIRECTOR_LOANS"], D("50000"))
        gate = next(i["includeWhen"] for i in CHECKLIST if i["id"] == "1AD.42")
        self.assertTrue(evaluate(gate, ctx))

    def test_without_lineage_director_loans_are_unknown_not_zero(self):
        ctx = build_note_context(dict(aggregate(*tb(FIXTURE_2))), NOTES, ALL_NO)
        self.assertIsNone(ctx["DIRECTOR_LOANS"])

    def test_unanswered_applicable_questions_block_final(self):
        ctx = build_note_context(aggregate(*tb(FIXTURE_2)), NOTES)
        hit = check_disclosure_answers(ctx, NOTES, CHECKLIST)
        self.assertEqual((hit.code, hit.severity), ("V-DISC-001", "CRITICAL"))
        self.assertIn("SUBSEQUENT_EVENTS", hit.message)

    def test_fully_answered_questionnaire_passes(self):
        ctx = build_note_context(aggregate(*tb(FIXTURE_2)), NOTES, ALL_NO)
        self.assertIsNone(check_disclosure_answers(ctx, NOTES, CHECKLIST))

    def test_note_needing_an_unanswered_fact_is_included_as_pending(self):
        ctx = build_note_context(aggregate(*tb(FIXTURE_2)), NOTES)
        self.assertIn("N9_COMMITMENTS", select_notes(NOTES, ctx))
        answered = build_note_context(aggregate(*tb(FIXTURE_2)), NOTES, ALL_NO)
        self.assertNotIn("N9_COMMITMENTS", select_notes(NOTES, answered))

    def test_unknown_answer_name_is_refused(self):
        with self.assertRaises(ValueError):
            build_note_context(aggregate(*tb(FIXTURE_2)), NOTES, {"HAS_EMPLOYESS": True})

    def test_every_checklist_condition_uses_declared_names(self):
        import re
        for item in CHECKLIST:
            names = set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", item.get("includeWhen", ""))) - {"AND", "OR", "NOT"}
            with self.subTest(item=item["id"]):
                self.assertLessEqual(names, DERIVED | ANSWER_FLAGS)


class ChecklistGatesMatchTopics(unittest.TestCase):
    """The (topic, condition) pairs for the directors' items, as corrected in v7.5.
    Changing one of these is a statutory decision: update this table deliberately
    and have the qualified reviewer sign off the pair."""
    ARR = ("DIRECTOR_LOANS != 0 OR DIRECTOR_LOAN_AGREEMENTS == true OR "
           "DIRECTOR_GUARANTEES == true OR DIRECTOR_GUARANTEE_AGREEMENTS == true")
    REVIEWED = {
        "1AD.35": "DIVIDENDS_PAID != 0", "1AD.37": None, "1AD.38": None,
        "1AD.39": "PAST_DIRECTOR_BENEFITS == true", "1AD.40": "THIRD_PARTY_DIRECTOR_SERVICES == true",
        "1AD.41": ARR, "1AD.42": "DIRECTOR_LOANS != 0 OR CONNECTED_LOANS != 0",
        "1AD.43": "DIRECTOR_LOAN_AGREEMENTS == true", "1AD.44": "DIRECTOR_GUARANTEES == true",
        "1AD.45": "DIRECTOR_GUARANTEE_AGREEMENTS == true", "1AD.46": ARR,
        "1AD.48": "DIRECTOR_MATERIAL_INTEREST == true", "1AD.49": "OWN_SHARES_HELD == true"}

    def test_reviewed_pairs(self):
        items = {i["id"]: i for i in CHECKLIST}
        for pid, cond in self.REVIEWED.items():
            with self.subTest(item=pid):
                self.assertEqual(items[pid].get("includeWhen"), cond)


class NoteTotalsEqualBalanceSheetLines(unittest.TestCase):
    POOL = ["FA_PLANT_COST", "FA_FIXTURES_COST", "FA_ACCUM_DEP", "FA_INTANGIBLE_COST", "FA_INVESTMENTS",
            "TRADE_DEBTORS", "OTHER_DEBTORS", "PREPAYMENTS", "VAT_CONTROL", "PAYE_PRSI", "CASH",
            "TRADE_CREDITORS", "ACCRUALS", "CORP_TAX", "LOANS_LT1Y", "LOANS_GT1Y",
            "LEASE_LIABILITY_LT1Y", "LEASE_LIABILITY_GT1Y", "DEFERRED_INCOME", "DIRECTOR_LOAN"]

    def test_property_note_totals_equal_their_sofp_lines(self):
        rng = random.Random(75)
        for n in range(300):
            bal = {k: str(D(rng.randint(-900000, 900000)) / 100) for k in rng.sample(self.POOL, 6)}
            bal["RETAINED_EARNINGS"] = str(-sum(D(v) for v in bal.values()))
            m = aggregate(*tb(bal))
            rows = {label: cur for label, cur, _ in build_sofp(m, {})["rows"]}
            ctx = build_note_context(m, NOTES, ALL_NO)
            with self.subTest(case=n):
                self.assertEqual(ctx["DEBTORS"], rows["Trade debtors"] + rows["Other debtors"])
                self.assertEqual(ctx["CREDITORS"], -(rows["Creditors: amounts falling due within one year"]
                                                     + rows["Lease liabilities"]
                                                     + rows["Creditors: amounts falling due after more than one year"]))
                self.assertEqual(ctx["FIXED_ASSETS_NBV"], rows["Intangible assets"] + rows["Tangible assets"]
                                 + rows["Fixed asset investments"])

    def test_lease_only_creditors_trigger_the_creditors_note(self):
        m = aggregate(*tb({"CASH": "10000", "LEASE_LIABILITY_LT1Y": "-3000",
                           "SHARE_CAPITAL": "-100", "RETAINED_EARNINGS": "-6900"}))
        ctx = build_note_context(m, NOTES, ALL_NO)
        self.assertEqual(ctx["CREDITORS"], D("3000"))
        self.assertIn("N4_CREDITORS", select_notes(NOTES, ctx))


class ExactBalanceChecks(unittest.TestCase):
    def test_one_cent_imbalance_fails_both_checks(self):
        lines, maps = tb({"CASH": "100.01", "SHARE_CAPITAL": "-100"})
        s = build_sofp(aggregate(lines, maps), {})
        self.assertFalse(check_tb_integrity(lines).passed)
        self.assertFalse(check_bs_balances(s).passed)
        self.assertEqual(check_bs_balances(s).passed, s["articulates"])


class ReviewRuleInputs(unittest.TestCase):
    def test_missing_profit_with_dividends_is_critical_not_skipped(self):
        hits = review_rules({"DIVIDENDS": D("1000000"), "RETAINED_EARNINGS": D("0")}, {}, None,
                            pack_path=RULES)
        self.assertIn(("R-DIV-001", "CRITICAL"), [(h.code, h.severity) for h in hits])

    def test_rules_require_the_pinned_pack(self):
        with self.assertRaises(TypeError):
            review_rules({}, {}, D("0"))  # pack_path is required
        with self.assertRaises(ValueError):
            load_review_rules(None)

    def test_director_rule_recognises_the_account_name_via_lineage(self):
        m = aggregate(*tb({"OTHER_CREDITORS": "-7800", "CASH": "7800"},
                          {"OTHER_CREDITORS": "Director's current account"}))
        codes = [h.code for h in review_rules(m, {}, D("0"), pack_path=RULES)]
        self.assertIn("R-DIR-001", codes)

    def test_missing_depreciation_rule_sees_every_fixed_asset_line(self):
        m = aggregate(*tb({"FA_FIXTURES_COST": "12000", "CASH": "-12000"}))
        codes = [h.code for h in review_rules(m, {}, D("0"), pack_path=RULES)]
        self.assertIn("R-DEP-001", codes)


class ComparativesAndPinning(unittest.TestCase):
    def test_one_depreciation_convention_no_double_count(self):
        pm = {"ADMIN_EXPENSES": D("100"), "DEPRECIATION_CHARGE": D("20"),
              "REVENUE": D("-500"), "RETAINED_EARNINGS": D("380")}
        prior = prior_from_mapped(pm)
        self.assertEqual((prior["ADMIN_EXPENSES"], prior["DEPRECIATION"]), (D("100"), D("20")))
        rows = {label: prev for label, _, prev in build_income_statement(pm, prior)["rows"]}
        self.assertEqual(rows["Administrative expenses (including depreciation)"], D("-120"))

    def test_pinning_compares_dates_not_strings(self):
        m = load_manifest()
        with self.assertRaises(ValueError):
            pin_pack_version({}, m, period_start="2025-12-31")
        pin_pack_version({}, m, period_start="2026-01-01")
        with self.assertRaises(ValueError):
            pin_pack_version({}, m, period_start="2026-1-1")  # malformed, refused

    def test_keywords_inside_string_literals_are_not_rewritten(self):
        self.assertTrue(evaluate("X == 'LAND AND BUILDINGS'", {"X": "LAND AND BUILDINGS"}))


if __name__ == "__main__":
    unittest.main()
