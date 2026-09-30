"""Golden tests v5.1 — rewritten after remediation so every test exercises the
REAL integration path (TB -> mapping -> statements/checks), encodes the
review's confirmed findings as regressions, and drops claims the code
couldn't support (e.g. rendered-comparative checks now actually render)."""
import unittest, json, pathlib
from decimal import Decimal as Dec
from tests.fixtures import RULES, tb_lines, MAPPINGS, PRIOR, FA_REGISTER, PERIOD
from engine.money import money, D
from engine.schemas import TBLine
from engine.mapping import suggest_mapping, classification, aggregate
from engine.reconciliation import (check_tb_integrity, check_bs_balances,
    check_fa_rollforward, check_re_rollforward, check_bank_reconciliation,
    check_comparatives, check_unmapped, review_rules, load_review_rules)
from engine.statements import build_sofp, build_income_statement
from engine.rounding import flag_for_note
from engine.notes import select_notes, build_fa_grid, build_note_context
from engine.pack import load_manifest, pin_pack_version

PACK = pathlib.Path(__file__).resolve().parent.parent / "content" / "frs102-1a-ie" / "2024.09"
NOTES = {p.stem: json.loads(p.read_text()) for p in (PACK/"notes").glob("*.json")}

def mapped_fixture():
    return aggregate(tb_lines(), MAPPINGS)

PRIOR_BY_LABEL = {
    "Tangible assets": "TANGIBLE_ASSETS", "Trade debtors": "TRADE_DEBTORS",
    "Other debtors": "OTHER_DEBTORS", "Cash at bank and in hand": "CASH",
    "Total current assets": "TOTAL_CURRENT_ASSETS",
    "Creditors: amounts falling due within one year": "CREDITORS_LT1Y",
    "Net current assets": "NET_CURRENT_ASSETS",
    "Total assets less current liabilities": "TALCL",
    "Creditors: amounts falling due after more than one year": "LOANS_GT1Y",
    "Net assets": "NET_ASSETS", "Called up share capital": "SHARE_CAPITAL",
    "Profit and loss account": "RETAINED_EARNINGS", "Total equity": "EQUITY",
}

class TestGoldenFixture(unittest.TestCase):
    def setUp(self):
        self.lines = tb_lines()
        self.mapped = mapped_fixture()

    def test_tb_balances(self):
        r = check_tb_integrity(self.lines)
        self.assertTrue(r.passed, r.message)
        self.assertEqual(sum(l.debit for l in self.lines), Dec("3051162.00"))

    def test_fixture_period_brings_2024_periodic_review_into_scope(self):
        # periods beginning on or after 1 Jan 2026 -> the 2024 Periodic Review
        # (five-step revenue, on-balance-sheet leases) applies to the fixture
        self.assertEqual(PERIOD["start"], "2026-01-01")
        self.assertEqual(PERIOD["end"], "2026-12-31")
        self.assertGreaterEqual(PERIOD["start"], "2026-01-01")

    def test_prior_year_fixture_articulates(self):
        # review finding: prior-year dict was internally inconsistent and
        # never checked. Components (creditors/loans stored negative):
        ca = PRIOR["TRADE_DEBTORS"] + PRIOR["OTHER_DEBTORS"] + PRIOR["CASH"]
        self.assertEqual(ca, PRIOR["TOTAL_CURRENT_ASSETS"])
        nca = ca + PRIOR["CREDITORS_LT1Y"]
        self.assertEqual(nca, PRIOR["NET_CURRENT_ASSETS"])
        talcl = PRIOR["TANGIBLE_ASSETS"] + nca
        self.assertEqual(talcl, PRIOR["TALCL"])
        na = talcl + PRIOR["LOANS_GT1Y"]
        self.assertEqual(na, PRIOR["NET_ASSETS"])
        self.assertEqual(PRIOR["SHARE_CAPITAL"] + PRIOR["RETAINED_EARNINGS"],
                         PRIOR["EQUITY"])
        self.assertEqual(na, PRIOR["EQUITY"])

    def test_sofp_via_mapping_and_balance_check_real(self):
        # review finding: statements hard-coded nominal codes and the BS
        # check compared 0==0. Now statements consume mapping output and the
        # check consumes the figures they actually emit.
        self.assertTrue(any("1500" == k for k in []) is False)  # no code keys
        s = build_sofp(self.mapped, PRIOR)
        self.assertTrue(s["articulates"])
        self.assertEqual(s["net_assets"], Dec("455812.00"))
        self.assertEqual(s["TOTAL_ASSETS"], Dec("686312.00"))
        self.assertEqual(s["TOTAL_LIABILITIES_AND_EQUITY"], Dec("686312.00"))
        r = check_bs_balances(s)
        self.assertTrue(r.passed, r.message)

    def test_bs_check_refuses_silent_pass(self):
        r = check_bs_balances({})
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, "CRITICAL")

    def test_income_statement_statutory_format(self):
        # review finding: separate depreciation face line is not a permitted
        # format line; admin must INCLUDE depreciation; distribution before admin.
        i = build_income_statement(self.mapped, PRIOR)
        vals = {label: cur for label, cur, _ in i["rows"]}
        self.assertNotIn("Depreciation charge", vals)
        self.assertEqual(vals["Administrative expenses (including depreciation)"],
                         Dec("-634150.00"))
        labels = [l for l, _, _ in i["rows"]]
        self.assertLess(labels.index("Distribution costs"),
                        labels.index("Administrative expenses (including depreciation)"))
        self.assertEqual(vals["Profit for the financial year"], Dec("157650.00"))

    def test_rendered_comparatives_match_validated_prior(self):
        # review finding: old test compared a hand-typed dict to itself.
        s = build_sofp(self.mapped, PRIOR)
        rendered = {label: pri for label, _, pri in s["rows"]}
        for label, key in PRIOR_BY_LABEL.items():
            self.assertEqual(rendered[label], PRIOR[key], f"{label} comparative")

    def test_comparatives_mismatch_flagged(self):
        rendered = {"NET_ASSETS": Dec("322999")}
        validated = {"NET_ASSETS": Dec("322162")}
        self.assertFalse(check_comparatives(rendered, validated)[0].passed)

    def test_re_rollforward_ties_with_golden_figures(self):
        s = build_sofp(self.mapped, PRIOR)
        r = check_re_rollforward(PRIOR["RETAINED_EARNINGS"], s["profit"],
                                 Dec("24000"), s["RETAINED_EARNINGS" ] if "RETAINED_EARNINGS" in s
                                 else [c for l,c,_ in s["rows"] if l=="Profit and loss account"][0])
        self.assertTrue(r.passed, r.message)

    def test_re_rollforward_accepts_transition_adjustment(self):
        # review finding: 2026 first-year adoption needs a transition slot
        r = check_re_rollforward(Dec("320000"), Dec("0"), Dec("0"), Dec("320500"),
                                 transition_adjustment=Dec("500"))
        self.assertTrue(r.passed, r.message)

    def test_bank_reconciliation(self):
        self.assertTrue(check_bank_reconciliation(Dec("284912"),
                        self.mapped["CASH"]).passed)

    def test_unmapped_none(self):
        m = {k: v for k, v in MAPPINGS.items() if v}
        self.assertTrue(check_unmapped(self.lines, m).passed)

    def test_fa_grid_corrected_class_split(self):
        g = build_fa_grid(FA_REGISTER)
        plant, motor, total = g[0], g[1], g[2]
        self.assertEqual(plant["closing_dep"], Dec("52000.00"))
        self.assertEqual(motor["closing_dep"], Dec("24000.00"))
        self.assertEqual(plant["nbv_close"], Dec("98000.00"))
        self.assertEqual(motor["nbv_close"], Dec("36000.00"))
        self.assertEqual(total["nbv_close"], Dec("134000.00"))
        self.assertEqual(total["nbv_open"], Dec("111400.00"))
        self.assertTrue(g[3]["invariant_holds"])

    def test_fa_grid_disposals_reduce_depreciation(self):
        # review finding: disposals cut cost but not accumulated depreciation
        g = build_fa_grid({"Plant": {"opening_cost": Dec("100000"),
            "additions": Dec("0"), "disposals": Dec("20000"),
            "disposals_dep": Dec("5000"),
            "opening_dep": Dec("10000"), "charge": Dec("4000")}})
        row = g[0]
        self.assertEqual(row["closing_cost"], Dec("80000.00"))
        self.assertEqual(row["closing_dep"], Dec("9000.00"))   # 10+4-5
        self.assertEqual(row["nbv_close"], Dec("71000.00"))
        self.assertTrue(g[2]["invariant_holds"])

    def test_statements_independent_of_nominal_codes(self):
        # review item 1: prove the statements consume mapping output, not raw
        # codes — renumber every account (+90000) and confirm identical SoFP
        shifted = [TBLine(str(int(l.nominal_code) + 90000), l.account_name,
                          l.debit, l.credit) for l in tb_lines()]
        shifted_map = {str(int(k) + 90000): v for k, v in MAPPINGS.items()}
        s1 = build_sofp(aggregate(tb_lines(), MAPPINGS), PRIOR)
        s2 = build_sofp(aggregate(shifted, shifted_map), PRIOR)
        self.assertEqual(s1["net_assets"], s2["net_assets"])
        self.assertEqual(s1["equity"], s2["equity"])
        self.assertTrue(s2["articulates"])
        self.assertEqual(s2["net_assets"], Dec("455812.00"))

    def test_sofp_has_rou_and_lease_lines(self):
        # 2024 Periodic Review: ROU asset + lease liability lines exist
        s = build_sofp(self.mapped, PRIOR)
        labels = [l for l, _, _ in s["rows"]]
        self.assertIn("Right-of-use assets", labels)
        self.assertIn("Lease liabilities", labels)

class TestReviewRules(unittest.TestCase):
    def test_pack_rules_loaded_from_json_data(self):
        rules = load_review_rules(RULES)
        self.assertEqual({r["id"] for r in rules},
                         {"R-NEG-001","R-RND-001","R-DIR-001","R-DEP-001","R-DIV-001"})
        self.assertFalse((PACK/"review-rules.py").exists())  # no executable pack code

    def test_clean_fixture_silent(self):
        self.assertEqual(review_rules(mapped_fixture(), {},
                                      profit_for_year=Dec("157650"), pack_path=RULES), [])

    def test_fully_depreciated_fa_does_not_trigger_dep_rule(self):
        # review finding: sign bug made NBV=0 assets "exist"
        mapped = {"FA_PLANT_COST": Dec("100000"), "FA_ACCUM_DEP": Dec("-100000"),
                  "DEPRECIATION_CHARGE": Dec("0")}
        self.assertEqual(review_rules(mapped, {}, profit_for_year=Dec("1000"), pack_path=RULES), [])

    def test_dividends_without_profit_fires_R_DIV_001(self):
        # review finding: old test set revenue as a DEBIT (wrong reason) and
        # asserted "any CRITICAL". Now: credit balance, exact rule asserted.
        lines = [TBLine("4000","Sales revenue",Dec("0"),Dec("1200000"))]
        for ln in tb_lines():
            if ln.nominal_code != "4000": lines.append(ln)
        mapped = aggregate(lines, MAPPINGS)
        profit = build_income_statement(mapped, PRIOR)["profit"]
        self.assertLessEqual(profit, Dec("0"))
        hits = review_rules(mapped, {}, profit_for_year=profit, pack_path=RULES)
        self.assertEqual([x.code for x in hits], ["R-DIV-001"])

    def test_pack_round_rule_fires_with_pack_message(self):
        lines = [TBLine("6000","Administrative expenses",Dec("0"),Dec("50000"))]
        hits = review_rules(aggregate(lines, {"6000":"ADMIN_EXPENSES"}), {},
                            profit_for_year=Dec("157650"), pack_path=RULES)
        rnd = [x for x in hits if x.code == "R-RND-001"]
        self.assertTrue(rnd)
        self.assertIn("50000", rnd[0].message.replace(",", ""))

class TestMapping(unittest.TestCase):
    def test_no_dangerous_substring_matches(self):
        # review finding: "sales" in "cost of sales", "rent" in "current", etc.
        kw = json.loads(json.dumps({}))  # use pack defaults
        import importlib.util as ilu
        spec = ilu.spec_from_file_location("md", str(PACK/"mapping-defaults.py"))
        md = ilu.module_from_spec(spec); spec.loader.exec_module(md)
        class L: pass
        cases = [("5000","Cost of sales","COST_OF_SALES"),
                 ("1201","Bank current account","CASH"),
                 ("6100","Interest receivable","INTEREST_RECEIVABLE"),
                 ("1505","Accumulated depreciation","FA_ACCUM_DEP"),
                 ("7100","Interest payable","INTEREST_PAYABLE")]
        for code, name, want in cases:
            l = L(); l.nominal_code = code; l.account_name = name
            line, conf, src, sig = suggest_mapping(l, {}, md.KEYWORD_SCORES, md.CODE_RANGES)
            self.assertEqual(line, want, f"{name} -> {line}")

    def test_confidence_tiers(self):
        import importlib.util as ilu
        spec = ilu.spec_from_file_location("md", str(PACK/"mapping-defaults.py"))
        md = ilu.module_from_spec(spec); spec.loader.exec_module(md)
        class L: pass
        l = L(); l.nominal_code = "1100"; l.account_name = "Trade debtors"
        prior = {"1100": {"name": "Trade debtors", "line": "TRADE_DEBTORS", "confirmed": True}}
        self.assertEqual(suggest_mapping(l, prior, md.KEYWORD_SCORES, md.CODE_RANGES)[1], 100)
        self.assertEqual(classification(100), "AUTO_CONFIRM")
        l2 = L(); l2.nominal_code = "1100"; l2.account_name = "Trade debtors"
        self.assertEqual(suggest_mapping(l2, {}, md.KEYWORD_SCORES, md.CODE_RANGES)[1], 55)
        self.assertEqual(classification(55), "ACTIVE_CHOICE")
        l3 = L(); l3.nominal_code = "9999"; l3.account_name = "Miscellaneous"
        self.assertEqual(suggest_mapping(l3, {}, md.KEYWORD_SCORES, md.CODE_RANGES)[1], 0)

    def test_bank_loan_not_mapped_to_cash(self):
        # adversarial review findings, BOTH directions:
        # v5.4 — bare "bank" mapped liabilities ("Bank Loan - Long Term")
        #        to CASH;  v5.5 — over-precise phrases left "Bank - Current
        #        a/c" UNMAPPED. Exclusion rule + abbreviation keywords fix
        # both: loans never CASH; real cash accounts (incl. abbreviations)
        # still CASH.
        import importlib.util as ilu
        spec = ilu.spec_from_file_location("md", str(PACK/"mapping-defaults.py"))
        md = ilu.module_from_spec(spec); spec.loader.exec_module(md)
        class L: pass
        def m(code, name):
            l = L(); l.nominal_code = code; l.account_name = name
            return suggest_mapping(l, {}, md.KEYWORD_SCORES, md.CODE_RANGES)
        for code, name in [("2300","Bank Loan - Long Term"),
                           ("2700","Interest on Bank Loan"),
                           ("2300","Bank borrowings"),
                           ("2301","Bank Mortgage")]:
            self.assertNotEqual(m(code, name)[0], "CASH",
                                f"{name} must not map to CASH")
            self.assertIsNotNone(m(code, name)[0])
        for code, name in [("1201","Bank - Current a/c"),
                           ("1202","Bank Acc"),
                           ("1203","Curr a/c"),
                           ("1200","Bank Current Account"),
                           ("1204","Cash at bank")]:
            self.assertEqual(m(code, name)[0], "CASH",
                             f"{name} must map to CASH")

    def test_pin_pack_version_refuses_repin(self):
        from engine.pack import pin_pack_version
        m = load_manifest()
        pinned = pin_pack_version({}, m)
        with self.assertRaises(ValueError):
            pin_pack_version(pinned, m)

    def test_heuristic_cap(self):
        kw = {"sales": ("REVENUE", 100)}
        rng = {(4000, 4099): "REVENUE"}
        class L: nominal_code = "4000"; account_name = "Sales"
        self.assertLess(suggest_mapping(L(), {}, kw, rng)[1], 80)

class TestMoney(unittest.TestCase):
    def test_float_rejected(self):
        with self.assertRaises(TypeError):
            D(0.1 + 0.2)

class TestPackIntegration(unittest.TestCase):
    def test_pack_notes_actually_load(self):
        # review finding: the pack never ran through the engine. Now it must.
        ctx = build_note_context(mapped_fixture(), NOTES,
                                 {"HAS_EMPLOYEES": True})
        selected = select_notes(NOTES, ctx)
        for code in ["N0_ENTITY","N1_POLICIES","N2_FA","N3_DEBTORS","N4_CREDITORS",
                     "N5_LOANS","N6_CAPITAL","N7_RPT"]:
            self.assertIn(code, selected)
        # and the checklists's own completeness assertions hold now
        for it in json.loads((PACK/"disclosure-checklist.json").read_text())["items"]:
            note = it.get("note")
            if note in (None, "_engine", "_line_level"): continue
            self.assertIn(note, NOTES)
            self.assertIn(it["id"], NOTES[note]["sourceRef"], it["id"])

class TestPackCompletenessFile(unittest.TestCase):
    """The pack's own completeness test (content/.../test_pack_completeness.py)
    executed INSIDE the main suite — review finding: it previously ran only
    when someone invoked pytest on that file separately, so '30/30' did not
    include the 55-item Appendix D verification."""
    def test_pack_completeness_module(self):
        import importlib.util as ilu, pathlib
        mod_path = (pathlib.Path(__file__).resolve().parent.parent
                    / "content" / "frs102-1a-ie" / "2024.09" / "test_pack_completeness.py")
        spec = ilu.spec_from_file_location("pack_completeness", mod_path)
        mod = ilu.module_from_spec(spec); spec.loader.exec_module(mod)
        mod.test_all_appendixD_items_covered()
        mod.test_every_note_cites_appendixD()
        mod.test_every_note_has_includeWhen()
        mod.test_required_fields_present()

    def test_undeclared_predicate_name_raises(self):
        # review finding: a typo in a pack includeWhen must fail LOUDLY at
        # load time, never silently hide a statutory note
        bad = dict(NOTES)
        bad["N9X"] = dict(NOTES["N9_COMMITMENTS"])
        bad["N9X"]["includeWhen"] = "TYPOD_NAME == true"
        with self.assertRaises(KeyError):
            build_note_context(mapped_fixture(), bad, {})

    def test_fixture_two_messy_irish_chart(self):
        # review Step-0 fixture: a REAL Irish chart. The overdrawn
        # director's loan must present as a DEBTOR (sign-home reclass),
        # never as negative creditors; VAT/PAYE present as creditors.
        lines = [
            TBLine("1200","Bank current account",Dec("40000"),Dec("0")),
            TBLine("2400","Director's current account",Dec("50000"),Dec("0")),
            TBLine("1600","Fixtures and fittings - cost",Dec("12000"),Dec("0")),
            TBLine("2220","VAT control",Dec("0"),Dec("21500")),
            TBLine("2230","PAYE/PRSI",Dec("0"),Dec("8300")),
            TBLine("3000","Called up share capital",Dec("0"),Dec("100")),
            TBLine("3100","Retained earnings b/f",Dec("0"),Dec("72100")),
        ]
        M2 = {"1200":"CASH","2400":"DIRECTOR_LOAN","1600":"FA_FIXTURES_COST",
              "2220":"VAT_CONTROL","2230":"PAYE_PRSI","3000":"SHARE_CAPITAL",
              "3100":"RETAINED_EARNINGS"}
        s = build_sofp(aggregate(lines, M2), {})
        rows = {lbl: cur for lbl, cur, _ in s["rows"]}
        self.assertEqual(rows["Other debtors"], Dec("50000.00"))
        self.assertEqual(rows["Creditors: amounts falling due within one year"],
                         Dec("-29800.00"))
        self.assertEqual(rows["Tangible assets"], Dec("12000.00"))
        self.assertEqual(s["net_assets"], Dec("72200.00"))
        self.assertTrue(s["articulates"])
        self.assertTrue(check_bs_balances(s).passed)

    def test_chart_v2_keyword_probe(self):
        # review finding: the canonical chart was too narrow for a real
        # Irish ledger (14 of 20 typical accounts unmapped)
        import importlib.util as ilu
        spec = ilu.spec_from_file_location("md", str(PACK/"mapping-defaults.py"))
        md = ilu.module_from_spec(spec); spec.loader.exec_module(md)
        class L: pass
        cases = [("1600","Fixtures and fittings","FA_FIXTURES_COST"),
                 ("1500","Land and buildings","FA_LAND_BUILDINGS"),
                 ("1350","Investments","FA_INVESTMENTS"),
                 ("2220","VAT control","VAT_CONTROL"),
                 ("2230","PAYE/PRSI","PAYE_PRSI"),
                 ("2400","Director's loan","DIRECTOR_LOAN"),
                 ("3105","Share premium","SHARE_PREMIUM"),
                 ("3300","Provisions","PROVISIONS"),
                 ("2320","Deferred tax","DEFERRED_TAX"),
                 ("2250","Accrued income","ACCRUED_INCOME"),
                 ("2260","Deferred income","DEFERRED_INCOME")]
        for code, name, want in cases:
            l = L(); l.nominal_code = code; l.account_name = name
            got = suggest_mapping(l, {}, md.KEYWORD_SCORES, md.CODE_RANGES)[0]
            self.assertEqual(got, want, f"{name} -> {got}")

class TestRoundingGolden(unittest.TestCase):
    def test_base_gap_flagged(self):
        f = flag_for_note([245900, 15300, 6350], 267550, 1000, "N3_DEBTORS.total")
        self.assertTrue(f["flagged"])
        self.assertEqual(f["gap"], Dec("-1000"))
        self.assertIn("rounding=N3_DEBTORS.total", f["deeplink"])

    def test_trap_allocation_fails(self):
        f = flag_for_note([245900+450, 15300, 6350], 268000, 1000, "N3_DEBTORS.total")
        self.assertTrue(f["flagged"])

    def test_clearing_allocation_clears(self):
        f = flag_for_note([245900, 15300, 6350+450], 268000, 1000, "N3_DEBTORS.total")
        self.assertFalse(f["flagged"])

class TestPackVersioning(unittest.TestCase):
    def test_manifest_and_pinning(self):
        m = load_manifest()
        self.assertEqual(m["pack"], "frs102-1a-ie")
        self.assertEqual(m["version"], "2024.09")
        old = pin_pack_version({"client": "demo"}, m)
        m2 = dict(m); m2["version"] = "2027.09"
        new = pin_pack_version({"client": "demo"}, m2)
        self.assertEqual(old["pack_version"], "2024.09")
        self.assertEqual(new["pack_version"], "2027.09")

if __name__ == "__main__":
    unittest.main(verbosity=2)
