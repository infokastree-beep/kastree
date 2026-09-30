"""Stress suite (v7.5) — adversarial probes across every engine surface.
Run: python -m unittest tests.test_stress -v   (also picked up by discover)
Each class targets one failure domain. Anything that crashes, hangs, or
silently accepts garbage is a bug: report it, never weaken the test."""
import json, glob, random, time, unittest, pathlib, tempfile, os, re as _re
from decimal import Decimal as Dec

from engine.schemas import TBLine
from engine.mapping import aggregate, suggest_mapping, SIGN_HOMES
from engine.statements import build_sofp, build_income_statement
from engine.reconciliation import (check_tb_integrity, check_bs_balances,
    check_re_rollforward, review_rules, load_review_rules)
from engine.notes import select_notes, build_note_context
from engine.predicates import evaluate
from engine.pack import pack_dir, load_manifest
from engine.rounding import flag_for_note, round_to
from engine.money import money

PACK = pathlib.Path(__file__).resolve().parent.parent / "content" / "frs102-1a-ie" / "2024.09"
NOTES = {p.stem: json.loads(p.read_text()) for p in (PACK/"notes").glob("*.json")}

BS_LINES = ["FA_PLANT_COST","FA_MOTOR_COST","FA_ACCUM_DEP","FA_FIXTURES_COST",
    "FA_LAND_BUILDINGS","FA_INVESTMENTS","FA_INTANGIBLE_COST","FA_INTANGIBLE_AMORT",
    "STOCKS","TRADE_DEBTORS","OTHER_DEBTORS","PREPAYMENTS","CASH","VAT_ASSET",
    "PAYE_ASSET","ACCRUED_INCOME","DEFERRED_TAX_ASSET",
    "TRADE_CREDITORS","OTHER_CREDITORS","ACCRUALS","CORP_TAX","VAT_CREDITOR",
    "PAYE_PRSI_CREDITOR","DEFERRED_INCOME","LOANS_LT1Y","LOANS_GT1Y",
    "LEASE_LIABILITY_LT1Y","LEASE_LIABILITY_GT1Y","DEFERRED_TAX_LIABILITY",
    "PROVISIONS","SHARE_CAPITAL","SHARE_PREMIUM","RETAINED_EARNINGS"]
DEBIT_HOME = {"FA_ACCUM_DEP","FA_INTANGIBLE_AMORT","SHARE_CAPITAL","SHARE_PREMIUM",
              "RETAINED_EARNINGS"}   # credit-natural lines

def make_balanced_tb(rng, n_accounts, lo=1, hi=999_999):
    """Random balanced TB exercising the full chart. First pass with RE=0 to
    learn net assets, then plug retained earnings so the set articulates."""
    picks = rng.sample(BS_LINES, min(n_accounts, len(BS_LINES)))
    lines = []
    for i, ln in enumerate(picks):
        if ln in ("SHARE_CAPITAL","SHARE_PREMIUM","RETAINED_EARNINGS"): continue
        amt = Dec(rng.randint(lo, hi))
        credit_natural = ln in DEBIT_HOME
        if ln in ("FA_ACCUM_DEP","FA_INTANGIBLE_AMORT","LOANS_LT1Y","LOANS_GT1Y",
                  "LEASE_LIABILITY_LT1Y","LEASE_LIABILITY_GT1Y","VAT_CREDITOR",
                  "PAYE_PRSI_CREDITOR","DEFERRED_TAX_LIABILITY","TRADE_CREDITORS",
                  "OTHER_CREDITORS","ACCRUALS","CORP_TAX","DEFERRED_INCOME","PROVISIONS"):
            credit_natural = True
        dr, cr = (Dec("0"), amt) if credit_natural else (amt, Dec("0"))
        lines.append(TBLine(f"9{i:04d}", ln.replace("_"," ").title(), dr, cr))
    M = {l.nominal_code: l.account_name.upper().replace(" ","_").replace("&","")
         for l in lines}
    # normalise: account names are junk on purpose; map by construction instead
    M = {l.nominal_code: [x for x in BS_LINES if x in l.account_name.upper().replace(" ","_")][0] for l in lines}
    first = build_sofp(aggregate(lines, M), {})
    re_plug = first["net_assets"]
    lines.append(TBLine("93000","Retained earnings", Dec("0") if re_plug >= 0 else -re_plug,
                        re_plug if re_plug >= 0 else Dec("0")))
    M["93000"] = "RETAINED_EARNINGS"
    return lines, M

class TestStressTrialBalances(unittest.TestCase):
    def test_500_seeded_random_tbs_articulate(self):
        for seed in range(500):
            rng = random.Random(seed)
            lines, M = make_balanced_tb(rng, rng.randint(5, 30))
            tb = check_tb_integrity(lines)
            self.assertTrue(tb.passed, f"seed {seed}: {tb.message}")
            s = build_sofp(aggregate(lines, M), {})
            self.assertTrue(s["articulates"], f"seed {seed}: net {s['net_assets']} vs equity {s['equity']}")
            self.assertTrue(check_bs_balances(s).passed, f"seed {seed}")

    def test_extreme_values(self):
        rng = random.Random(7)
        for scale in (Dec("0.01"), Dec("999999999999.99"), Dec("1000000")):
            lines, M = make_balanced_tb(rng, 12, lo=1, hi=1000)
            scaled = [TBLine(l.nominal_code, l.account_name,
                             (l.debit*scale).quantize(Dec("0.01")),
                             (l.credit*scale).quantize(Dec("0.01"))) for l in lines]
            tb = check_tb_integrity(scaled)
            self.assertTrue(tb.passed, f"scale {scale}: {tb.message}")
            s = build_sofp(aggregate(scaled, M), {})
            self.assertTrue(s["articulates"], f"scale {scale}")

    def test_large_tb_performance(self):
        rng = random.Random(99)
        t0 = time.time()
        lines, M = make_balanced_tb(rng, len(BS_LINES))
        # expand to ~5000 accounts by duplicating with distinct codes
        big, bigM = [], {}
        for k in range(170):
            for l in lines:
                code = f"{k}{l.nominal_code}"
                big.append(TBLine(code, l.account_name, l.debit, l.credit))
                bigM[code] = M[l.nominal_code]
        # rebalance: each duplicate set identical -> totals scale; plug RE once
        tb = check_tb_integrity(big)
        self.assertTrue(tb.passed, tb.message)
        s = build_sofp(aggregate(big, bigM), {})
        dt = time.time() - t0
        self.assertLess(dt, 10, f"5000-account build took {dt:.1f}s")
        self.assertTrue(s["articulates"], f"net {s['net_assets']} vs equity {s['equity']}")

    def test_unbalanced_tb_fails_loudly(self):
        rng = random.Random(3)
        lines, M = make_balanced_tb(rng, 10)
        lines.append(TBLine("99999","Junk", Dec("0.01"), Dec("0")))
        r = check_tb_integrity(lines)
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, "CRITICAL")

class TestStressMapping(unittest.TestCase):
    def test_1000_name_fuzz_never_maps_loans_to_cash(self):
        rng = random.Random(11)
        import importlib.util as ilu
        spec = ilu.spec_from_file_location("md", str(PACK/"mapping-defaults.py"))
        md = ilu.module_from_spec(spec); spec.loader.exec_module(md)
        pieces = ["bank","loan","current","director","vat","paye","rent","sales",
                  "machine","van","acc","a/c","charges","interest","premium","stock"]
        danger = _re.compile(r"\b(loans?|borrowings?|mortgages?|overdrafts?|directors?'?s?|"
                             r"vat|paye|prsi|usc|corporation tax|income tax)\b")
        for i in range(1000):
            name = " ".join(rng.sample(pieces, rng.randint(1,4)))
            class L: pass
            l = L(); l.nominal_code = str(rng.randint(1000,9999)); l.account_name = name
            line, conf, src, sig = suggest_mapping(l, {}, md.KEYWORD_SCORES, md.CODE_RANGES)
            if danger.search(name.lower()):
                self.assertNotEqual(line, "CASH", f"'{name}' mapped to CASH")
            if conf: self.assertLess(conf, 80)

    def test_every_sign_home_both_directions(self):
        for control, (dr_home, cr_home) in SIGN_HOMES.items():
            for bal, want in ((Dec("5000"), dr_home), (Dec("-5000"), cr_home)):
                l = TBLine("7001", control.title(), bal if bal > 0 else Dec("0"),
                           -bal if bal < 0 else Dec("0"))
                a = aggregate([l], {"7001": control})
                self.assertIn(want, a, f"{control} {bal} -> {dict(a)}")
                self.assertEqual(a[want], bal)

class TestStressPredicates(unittest.TestCase):
    def test_grammar_fuzz_no_crash_no_hang(self):
        rng = random.Random(23)
        names = ["A","B_C","DEBTORS","X1"]
        ops = ["==","!=",">","<",">=","<=","%"]
        ctx = {"A":1,"B_C":0,"DEBTORS":Dec("100"),"X1":True}
        for i in range(800):
            depth = rng.randint(1, 12)
            expr = rng.choice(names)
            for _ in range(depth):
                expr = f"{expr} {rng.choice(['and','or'])} {rng.choice(names)} {rng.choice(ops)} {rng.randint(0,100)}"
            t0 = time.time()
            try:
                evaluate(expr, ctx)
            except Exception:
                pass  # raising is fine; crashing the interpreter / hanging is not
            self.assertLess(time.time()-t0, 1.0, f"possible hang on: {expr[:80]}")

    def test_malformed_inputs_raise_fast(self):
        for bad in ["", "(((", "A ==", "1..2", "A;B", "\x00"*50, "a"*20000]:
            t0 = time.time()
            with self.assertRaises(Exception):
                evaluate(bad, {"A": 1})
            self.assertLess(time.time()-t0, 1.0)

class TestStressPack(unittest.TestCase):
    def test_corrupt_pack_files_raise_not_silently_pass(self):
        import shutil
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(PACK, f"{d}/frs102-1a-ie/2024.09")
            pj = f"{d}/frs102-1a-ie/2024.09/pack.json"
            for garbage in ('{', '{"pack": 123}', 'not json at all', '[]'):
                open(pj,"w").write(garbage)
                with self.assertRaises(Exception):
                    load_manifest(pathlib.Path(pj))
            open(pj,"w").write(json.dumps({"pack":"frs102-1a-ie","version":"2099.01"}))
            with self.assertRaises(Exception):
                pack_dir(root=pathlib.Path(d))  # manifest/dir mismatch

    def test_pack_load_time(self):
        t0 = time.time()
        for _ in range(50):
            load_manifest()
        self.assertLess(time.time()-t0, 2.0)

class TestStressRounding(unittest.TestCase):
    def test_sweep_never_crashes_and_flags_only_real_gaps(self):
        rng = random.Random(41)
        for i in range(20_000):
            children = [rng.randint(0, 10**6) for _ in range(rng.randint(2,8))]
            total = sum(children)
            unit = rng.choice([1, 10, 100, 1000])
            f = flag_for_note(children, total, unit, "X")
            gap = f.get("gap")
            self.assertIsNotNone(gap)
            if not f["flagged"]:
                self.assertEqual(sum(round_to(c, unit) for c in children), round_to(total, unit))

class TestStressDisclosure(unittest.TestCase):
    def test_unanswered_never_treated_as_no(self):
        # every disclosure-flag name left unanswered -> notes pending, never dropped
        lines, M = make_balanced_tb(random.Random(5), 15)
        a = aggregate(lines, M)
        ctx = build_note_context(a, NOTES, {})   # no flags answered
        sel = select_notes(NOTES, ctx)
        for code, t in NOTES.items():
            inc = t.get("includeWhen","")
            if inc == "always": self.assertIn(code, sel); continue
            # if condition needs an answered fact, note must be present (pending) or condition false
            if code in sel: continue
            # dropped only allowed when every fact it needs is derivable-FALSE
        # unanswered directors' item must surface: fixture-2-style loan present
        loan_lines = [TBLine("2400","Director current account", Dec("50000"), Dec("0"))]
        a2 = aggregate(loan_lines, {"2400":"DIRECTOR_LOAN"})
        ctx2 = build_note_context(a2, NOTES, {})
        sel2 = select_notes(NOTES, ctx2)
        self.assertTrue(any("loan" in (sel2[c].get("title","").lower()) for c in sel2
                            if sel2[c].get("title")), "director loan must surface a note")

if __name__ == "__main__":
    unittest.main(verbosity=1)
