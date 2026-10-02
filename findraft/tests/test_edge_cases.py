"""Edge-case suite for the v5.5 review (test vectors 1-7 and 10).

Vectors 8 (rendering security) and 9 (tenant isolation) target the service
layer, which is not in the build pack; they are not executable here.
Stdlib only: property tests use a seeded RNG so failures are reproducible.
"""
import importlib.util as ilu
import json
import pathlib
import random
import unittest
from decimal import Decimal as Dec

from engine.mapping import aggregate, suggest_mapping
from engine.notes import ANSWER_FLAGS, build_note_context, select_notes
from engine.pack import load_manifest, pin_pack_version
from engine.predicates import evaluate
from engine.reconciliation import check_bs_balances, check_tb_integrity, review_rules
from engine.rounding import flag_for_note, rounding_gap
from engine.schemas import TBLine
from engine.statements import build_income_statement, build_sofp
from tests.fixtures import RULES, MAPPINGS, PRIOR, tb_lines

PACK = pathlib.Path(__file__).resolve().parent.parent / "content" / "frs102-1a-ie" / "2024.09"
NOTES = {p.stem: json.loads(p.read_text(encoding="utf-8"))
         for p in (PACK / "notes").glob("*.json")}


def _load_py(name: str):
    spec = ilu.spec_from_file_location(name, str(PACK / f"{name}.py"))
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MD = _load_py("mapping-defaults")
POLICIES = _load_py("policies").POLICIES


def _tb_from_balances(balances: dict) -> tuple[list, dict]:
    """canonical_line -> debit-positive balance  =>  (TB lines, mappings)."""
    lines, maps = [], {}
    for i, (canon, bal) in enumerate(sorted(balances.items())):
        code = str(10000 + i)
        dr, cr = (bal, Dec("0")) if bal >= 0 else (Dec("0"), -bal)
        lines.append(TBLine(code, canon.title(), dr, cr))
        maps[code] = canon
    return lines, maps


# ---------------------------------------------------------------- vector 1
PRESENTABLE = ["FA_PLANT_COST", "FA_MOTOR_COST", "FA_ACCUM_DEP", "STOCKS",
               "TRADE_DEBTORS", "OTHER_DEBTORS", "PREPAYMENTS", "CASH",
               "TRADE_CREDITORS", "OTHER_CREDITORS", "ACCRUALS", "CORP_TAX",
               "LOANS_LT1Y", "LOANS_GT1Y", "SHARE_CAPITAL", "REVENUE",
               "COST_OF_SALES", "DISTRIBUTION_COSTS", "ADMIN_EXPENSES",
               "DEPRECIATION_CHARGE", "OTHER_OPERATING_INCOME",
               "INTEREST_RECEIVABLE", "INTEREST_PAYABLE", "TAX_CHARGE",
               "DIVIDENDS", "ROU_ASSETS", "LEASE_LIABILITY_LT1Y",
               "LEASE_LIABILITY_GT1Y",
               # chart v2 (v6.8) incl. sign-home source lines
               "FA_FIXTURES_COST", "FA_LAND_BUILDINGS", "FA_INVESTMENTS",
               "FA_INTANGIBLE_COST", "FA_INTANGIBLE_AMORT", "BANK_OVERDRAFT",
               "PROVISIONS", "SHARE_PREMIUM", "ACCRUED_INCOME", "DEFERRED_INCOME",
               "DIRECTOR_LOAN", "VAT_CONTROL", "PAYE_PRSI", "DEFERRED_TAX"]
STRAY = ["ADMIN_EXPENSES_RENT", "ADMIN_EXPENSES_STAFF", "LOANS"]


class V1MoneyConservation(unittest.TestCase):
    """Balanced TB in => SoFP balances, or the engine refuses. Never a
    silently wrong statement; SoFP profit always equals IS profit."""

    def _random_case(self, rng: random.Random, allow_stray: bool) -> dict:
        pool = PRESENTABLE + (STRAY if allow_stray else [])
        bal = {k: Dec(rng.randint(-5_000_000, 5_000_000)) / 100
               for k in rng.sample(pool, rng.randint(1, len(pool)))}
        bal["RETAINED_EARNINGS"] = -sum(bal.values(), Dec("0"))  # plug
        return bal

    def _run(self, allow_stray: bool) -> None:
        rng = random.Random(20260927 + allow_stray)
        for n in range(500):
            lines, maps = _tb_from_balances(self._random_case(rng, allow_stray))
            self.assertTrue(check_tb_integrity(lines).passed)
            mapped = aggregate(lines, maps)
            try:
                s = build_sofp(mapped, {})
            except ValueError:
                continue  # loud refusal is acceptable
            with self.subTest(case=n):
                self.assertTrue(check_bs_balances(s).passed,
                                f"imbalance: {sorted(mapped)}")
                self.assertEqual(s["profit"],
                                 build_income_statement(mapped, {})["profit"])

    def test_presentable_lines_only(self):
        self._run(allow_stray=False)

    def test_with_unpresentable_lines(self):
        self._run(allow_stray=True)


# ---------------------------------------------------------------- vector 2
class V2OverdrawnBank(unittest.TestCase):
    CL = "Creditors: amounts falling due within one year"
    CASH = "Cash at bank and in hand"

    def _sofp(self, extra: list) -> dict:
        lines = tb_lines() + [ln for ln, _ in extra]
        maps = dict(MAPPINGS, **{ln.nominal_code: c for ln, c in extra})
        return build_sofp(aggregate(lines, maps), PRIOR)

    @staticmethod
    def _row(s: dict, label: str) -> Dec:
        return next(c for lbl, c, _ in s["rows"] if lbl == label)

    def test_single_overdrawn_account_is_a_creditor(self):
        base = self._sofp([])
        s = self._sofp([(TBLine("2131", "Bank No.2", Dec("0"), Dec("5000")), "CASH"),
                        (TBLine("2111", "Sundry debtor", Dec("5000"), Dec("0")), "OTHER_DEBTORS")])
        self.assertTrue(check_bs_balances(s).passed)
        self.assertEqual(self._row(s, self.CASH), self._row(base, self.CASH))
        self.assertEqual(self._row(s, self.CL), self._row(base, self.CL) - Dec("5000"))

    def test_no_offset_between_bank_accounts(self):
        # +10,000 in one account and -15,000 in another: Sch 3A forbids set-off
        base = self._sofp([])
        s = self._sofp([(TBLine("2131", "Bank No.2", Dec("10000"), Dec("0")), "CASH"),
                        (TBLine("2132", "Bank No.3", Dec("0"), Dec("15000")), "CASH"),
                        (TBLine("2111", "Sundry debtor", Dec("5000"), Dec("0")), "OTHER_DEBTORS")])
        self.assertTrue(check_bs_balances(s).passed)
        self.assertEqual(self._row(s, self.CASH), self._row(base, self.CASH) + Dec("10000"))
        self.assertEqual(self._row(s, self.CL), self._row(base, self.CL) - Dec("15000"))


# ---------------------------------------------------------------- vector 3
class V3DividendLegality(unittest.TestCase):
    """Distributable profits = accumulated realised profits (CA 2014 s.117),
    proxied by opening P&L reserve + profit for the year."""

    def _hits(self, opening_re: str, profit: str, dividend: str) -> list:
        mapped = {"RETAINED_EARNINGS": -Dec(opening_re), "DIVIDENDS": Dec(dividend)}
        return [h.code for h in review_rules(mapped, {}, profit_for_year=Dec(profit), pack_path=RULES)]

    def test_dividend_exactly_equal_to_reserves_is_lawful(self):
        self.assertEqual(self._hits("20000", "-5000", "15000"), [])

    def test_one_euro_over_reserves_is_critical(self):
        self.assertEqual(self._hits("20000", "-5000", "15001"), ["R-DIV-001"])

    def test_profitable_year_with_accumulated_deficit_is_critical(self):
        self.assertEqual(self._hits("-50000", "30000", "1"), ["R-DIV-001"])

    def test_no_dividend_never_fires(self):
        self.assertEqual(self._hits("-50000", "-30000", "0"), [])


# ---------------------------------------------------------------- vector 4
BALANCE_SHEET = {"CASH", "FA_PLANT_COST", "FA_MOTOR_COST", "FA_ACCUM_DEP",
                 "LOANS", "LOANS_LT1Y", "LOANS_GT1Y", "TRADE_DEBTORS",
                 "OTHER_DEBTORS", "STOCKS"}


class V4MappingAdversarial(unittest.TestCase):
    @staticmethod
    def _map(code: str, name: str):
        class L:
            nominal_code = code
            account_name = name
        return suggest_mapping(L(), {}, MD.KEYWORD_SCORES, MD.CODE_RANGES)[0]

    def test_pl_accounts_never_map_to_balance_sheet(self):
        for name in ["Motor expenses", "Loan interest", "Bank charges",
                     "Cash discounts allowed", "Interest on Bank Loan"]:
            for code in ["9901", "7600"]:  # no range / overhead range
                with self.subTest(name=name, code=code):
                    self.assertNotIn(self._map(code, name), BALANCE_SHEET)

    def test_director_account_never_cash(self):
        for name in ["Directors current a/c", "Director's current account",
                     "Director loan account"]:
            with self.subTest(name=name):
                self.assertNotEqual(self._map("1150", name), "CASH")

    def test_revenue_commissioners_is_not_turnover(self):
        self.assertNotIn(self._map("2202", "Revenue Commissioners - VAT"),
                         {"REVENUE", "CASH"})

    def test_malformed_codes_and_names_do_not_crash(self):
        for code, name in [("1200-01", "Bank current account"), (" 1200 ", "Bank"),
                           ("", ""), ("ABC", "   "), ("1200", "Bank (€) a/c [old]")]:
            with self.subTest(code=code, name=name):
                self._map(code, name)

    def test_real_cash_accounts_still_cash(self):
        for name in ["Bank - Current a/c", "Petty cash", "Cash at bank"]:
            with self.subTest(name=name):
                self.assertEqual(self._map("1201", name), "CASH")


# ---------------------------------------------------------------- vector 5
class V5PackPinning(unittest.TestCase):
    def test_db_row_with_null_pack_version_can_be_pinned(self):
        row = pin_pack_version({"id": 1, "pack_id": None, "pack_version": None},
                               load_manifest())
        self.assertEqual(row["pack_version"], "2024.09")

    def test_repin_refused(self):
        with self.assertRaises(ValueError):
            pin_pack_version({"pack_version": "2024.09"}, load_manifest())

    def test_period_before_pack_effective_date_refused(self):
        with self.assertRaises(ValueError):
            pin_pack_version({}, load_manifest(), period_start="2025-07-01")

    def test_period_on_effective_date_accepted(self):
        pin_pack_version({}, load_manifest(), period_start="2026-01-01")


# ---------------------------------------------------------------- vector 6
class V6NoteSelection(unittest.TestCase):
    def _selected(self, flags: dict | None = None) -> set:
        mapped = aggregate(tb_lines(), MAPPINGS)
        return set(select_notes(NOTES, build_note_context(mapped, NOTES, flags)))

    def test_employees_note_always_present(self):
        self.assertIn("N8_EMPLOYEES", self._selected())

    def test_each_n9_trigger_includes_n9_alone(self):
        for flag in ["PENSION_COMMITMENT", "CHARGES_EXIST", "OFF_BALANCE_ARRANGEMENT",
                     "COMMITMENTS_EXIST", "GUARANTEES_EXIST", "SUBSEQUENT_EVENTS"]:
            with self.subTest(flag=flag):
                self.assertIn("N9_COMMITMENTS", self._selected({flag: True}))

    def test_template_without_includewhen_is_an_error(self):
        with self.assertRaises(ValueError):
            select_notes({"NX": {"title": "orphan"}}, {})

    def test_leases_policy_follows_lease_balances(self):
        mapped = dict(aggregate(tb_lines(), MAPPINGS), ROU_ASSETS=Dec("9000"),
                      LEASE_LIABILITY_GT1Y=Dec("-9000"))
        self.assertTrue(build_note_context(mapped, NOTES)["HAS_LEASES"])


# ---------------------------------------------------------------- vector 7
class V7PackDslFuzz(unittest.TestCase):
    """Every predicate the pack ships must evaluate against the real
    context: no KeyError / ValueError from typos or undefined names."""

    def _ctx(self) -> dict:
        # every questionnaire answer supplied: this test is about names resolving
        return build_note_context(aggregate(tb_lines(), MAPPINGS), NOTES,
                                  {n: False for n in ANSWER_FLAGS})

    def _check(self, where: str, expr: str) -> None:
        if expr in (None, "", "always"):
            return
        try:
            evaluate(expr, self._ctx())
        except (KeyError, ValueError) as e:
            self.fail(f"{where}: {expr!r} -> {e}")

    def test_checklist_predicates(self):
        items = json.loads((PACK / "disclosure-checklist.json")
                           .read_text(encoding="utf-8"))["items"]
        for it in items:
            with self.subTest(item=it["id"]):
                self._check(it["id"], it.get("includeWhen"))

    def test_note_predicates(self):
        for code, t in NOTES.items():
            with self.subTest(note=code):
                self._check(code, t.get("includeWhen"))

    def test_policy_predicates(self):
        for p in POLICIES:
            with self.subTest(policy=p["id"]):
                self._check(p["id"], p["appliesWhen"])

    def test_review_rule_predicates(self):
        rules = json.loads((PACK / "review-rules.json").read_text(encoding="utf-8"))["rules"]
        line_ctx = {"balance": Dec("0"), "category": "EXPENSE", "is_director_line": False}
        client_ctx = {"has_fixed_assets": True, "has_depreciation": True,
                      "dividends": Dec("0"), "profit_for_year": Dec("0"),
                      "opening_re": Dec("0")}
        for r in rules:
            with self.subTest(rule=r["id"]):
                evaluate(r["when"], client_ctx if r["scope"] == "client" else line_ctx)


# --------------------------------------------------------------- vector 10
class V10RoundingNegatives(unittest.TestCase):
    def test_sign_symmetry(self):
        rng = random.Random(7)
        for _ in range(300):
            kids = [Dec(rng.randint(-900_000, 900_000)) for _ in range(rng.randint(1, 6))]
            total = sum(kids, Dec("0"))
            for unit in (1, 1000):
                with self.subTest(kids=kids, unit=unit):
                    self.assertEqual(rounding_gap([-k for k in kids], -total, unit),
                                     -rounding_gap(kids, total, unit))

    def test_negative_half_case_flagged(self):
        f = flag_for_note([Dec("-1500"), Dec("-1500")], Dec("-3000"), 1000, "N4.total")
        self.assertTrue(f["flagged"])
        self.assertEqual(f["gap"], Dec("-1000"))

    def test_deeplink_encodes_reserved_characters(self):
        link = flag_for_note([Dec("1.4")], Dec("2"), 1, "N4#a&b=c")["deeplink"]
        self.assertEqual(link.count("&"), 1)
        self.assertNotIn("#", link)


if __name__ == "__main__":
    unittest.main(verbosity=2)
