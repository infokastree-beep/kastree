"""Deterministic reconciliation engine. (Spec §4.4 Step 4, §4.8)
Every check returns CheckResult; nothing here may ever call an LLM."""
from . import lines as L
from dataclasses import dataclass
from decimal import Decimal as Dec
from .money import close

@dataclass(frozen=True)
class CheckResult:
    code: str
    severity: str          # PASS | CRITICAL | WARNING | BLOCKED
    passed: bool
    message: str

def check_prior_year_gate(prior_year_validated: bool) -> CheckResult | None:
    """Hard gate (cursorrules §4): reconciliation is BLOCKED until the
    prior year is confirmed & locked. Callers must stop on a non-None result."""
    if prior_year_validated is True:
        return None
    return CheckResult("V-GATE-001", "BLOCKED", False,
                       "Prior-year data not validated — reconciliation blocked")

def check_tb_integrity(tb_lines) -> CheckResult:
    dr = sum((l.debit for l in tb_lines), Dec("0.00"))
    cr = sum((l.credit for l in tb_lines), Dec("0.00"))
    ok = dr == cr  # exact: ledger exports are exact to the cent
    return CheckResult("V-TB-001", "PASS" if ok else "CRITICAL", ok,
                       f"TB debits {dr:,.2f} vs credits {cr:,.2f}")

def check_bs_balances(figures: dict) -> CheckResult:
    """v5.1: FAILS LOUDLY if the balance figures are absent — the previous
    version defaulted missing keys to 0 and silently passed 0 == 0."""
    if "TOTAL_ASSETS" not in figures or "TOTAL_LIABILITIES_AND_EQUITY" not in figures:
        return CheckResult("V-BS-001", "CRITICAL", False,
            "Balance figures not supplied to check — refusing silent pass")
    assets = figures["TOTAL_ASSETS"]; liab_eq = figures["TOTAL_LIABILITIES_AND_EQUITY"]
    ok = assets == liab_eq  # exact, identical to build_sofp's "articulates"
    return CheckResult("V-BS-001", "PASS" if ok else "CRITICAL", ok,
                       f"Assets {assets:,.2f} vs liabilities+equity {liab_eq:,.2f}")

def check_fa_rollforward(opening_nbv, additions, depreciation, disposals,
                         closing_nbv) -> CheckResult:
    expected = opening_nbv + additions - depreciation - disposals
    ok = close(expected, closing_nbv)
    return CheckResult("V-FA-001", "PASS" if ok else "WARNING", ok,
                       f"FA roll-forward: {opening_nbv:,.0f} + {additions:,.0f} - "
                       f"{depreciation:,.0f} - {disposals:,.0f} = {expected:,.0f} "
                       f"vs closing {closing_nbv:,.0f}")

def check_re_rollforward(opening_re, profit, dividends, closing_re,
                         transition_adjustment=None) -> CheckResult:
    """transition_adjustment: first-year-adoption cumulative effect taken to
    opening RE (FRS 102 paras 1.47 / 1.61) — absent from the check until v5.1."""
    adj = transition_adjustment if transition_adjustment is not None else Dec("0")
    expected = opening_re + adj + profit - dividends
    ok = close(expected, closing_re)
    return CheckResult("V-RE-001", "PASS" if ok else "CRITICAL", ok,
                       f"RE: {opening_re:,.0f} + {profit:,.0f} - {dividends:,.0f} "
                       f"= {expected:,.0f} vs closing {closing_re:,.0f}")

def check_bank_reconciliation(statement_balance, tb_bank) -> CheckResult:
    ok = close(statement_balance, tb_bank)
    return CheckResult("V-BANK-001", "PASS" if ok else "WARNING", ok,
                       f"Bank statement {statement_balance:,.2f} vs TB {tb_bank:,.2f}")

def check_comparatives(current: dict, prior_validated: dict) -> list:
    """Each present comparative must match the validated prior-year figure
    (hard-gate dependency: prior_year_validated)."""
    out = []
    for k in sorted(set(current) - set(prior_validated)):
        if current[k] != 0:
            out.append(CheckResult("V-CMP-002", "WARNING", False,
                                   f"Comparative missing for mapped line {k}"))
    for k, v in prior_validated.items():
        cur = current.get(k)
        ok = cur is not None and close(cur, v)
        out.append(CheckResult("V-CMP-001", "PASS" if ok else "WARNING", ok,
                    f"Comparative {k}: current {cur} vs validated prior {v}"))
    return out

def check_unmapped(tb_lines, mappings: dict) -> CheckResult:
    unmapped = [l.nominal_code for l in tb_lines
                if l.nominal_code not in mappings or not mappings[l.nominal_code]]
    ok = not unmapped
    return CheckResult("V-MAP-001", "PASS" if ok else "CRITICAL", ok,
                       "All codes mapped" if ok else f"Unmapped: {unmapped}")

# ---- Review rules: loaded and executed from the content pack (single source of truth) ----
import functools as _functools
import json as _json
import re as _re
import pathlib as _pl
from .predicates import evaluate, Unanswered

EXPENSE_LINES = L.EXPENSES
FA_LINES = L.FIXED_ASSETS  # every fixed-asset line, incl. fixtures, land & buildings, investments
# Contained pack-rule failures FAIL CLOSED: a rule that cannot be evaluated
# is reported as CRITICAL (blocks FINAL), never downgraded to a non-blocking state.
_RULE_FAILURES = (ValueError, KeyError, TypeError, ArithmeticError, Unanswered)

@_functools.lru_cache(maxsize=32)
def _read_rules(path: str) -> tuple:
    return tuple(_json.loads(_pl.Path(path).read_text(encoding="utf-8"))["rules"])


def load_review_rules(pack_path) -> list:
    """Review rules of ONE pinned pack version (JSON data, never executed).
    There is deliberately no default: the caller passes the draft's pinned pack
    (engine.pack.pack_dir(pack_id, version) / "review-rules.json"), so version
    pinning cannot be bypassed by omission. Packs are immutable, so reads are cached."""
    if pack_path is None:
        raise ValueError("review rules need the draft's pinned pack path — no default")
    return [dict(r) for r in _read_rules(str(_pl.Path(pack_path).resolve()))]


_FIELD = _re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _render(template: str, ctx: dict) -> str:
    # never str.format() on pack text: '{x.__class__...}' walks attributes
    return _FIELD.sub(lambda m: str(ctx.get(m.group(1), m.group(0))), template)

def review_rules(mapped: dict, descriptions: dict, profit_for_year: Dec, *,
                 pack_path, opening_re=None) -> list:
    """Evaluate the pinned pack's review rules. mapped: canonical_line -> balance
    (an engine.mapping.Aggregated also carries lineage). Every input is
    required: a rule whose input is missing is reported CRITICAL (fail closed),
    never skipped. Director lines are recognised from `descriptions` (keyed by
    canonical line) OR from the contributing TB account names (lineage)."""
    rules = load_review_rules(pack_path)
    sources = getattr(mapped, "sources", {})

    def is_director(line: str) -> bool:
        names = [descriptions.get(line, "")] + [s.account_name for s in sources.get(line, [])]
        names += [s.source_line for s in sources.get(line, [])]
        return any(_re.search(r"\bdirectors?\b|director's|DIRECTOR_LOAN", n, _re.I) for n in names)
    out = []
    def b(line): return mapped.get(line, Dec("0"))
    client_ctx = {
        "has_fixed_assets": sum((b(k) for k in sorted(FA_LINES)), Dec("0")) != 0,
        "has_depreciation": b("DEPRECIATION_CHARGE") != 0,
        "dividends": b("DIVIDENDS"),
        # proxy for distributable reserves (s.117 CA 2014): opening P&L reserve
        "opening_re": opening_re if opening_re is not None else -b("RETAINED_EARNINGS"),
        "profit_for_year": profit_for_year,  # None => the rule fails closed below
    }
    for rule in rules:
        if rule["scope"] == "client":
            try:
                fired = evaluate(rule["when"], client_ctx)
            except _RULE_FAILURES as e:  # contained, fail closed
                out.append(CheckResult(rule["id"], "CRITICAL", False,
                                       f"pack rule could not be evaluated: {e}"))
                continue
            if fired:
                out.append(CheckResult(rule["id"], rule["severity"], False,
                                       _render(rule["message"], client_ctx)))
        else:
            for line, bal in mapped.items():
                ctx = {"balance": bal,
                       "category": ("EXPENSE" if line in EXPENSE_LINES else
                                    ("ASSET" if line in FA_LINES else "OTHER")),
                       "is_director_line": is_director(line)}
                try:
                    fired = evaluate(rule["when"], ctx)
                except _RULE_FAILURES as e:  # contained, fail closed
                    out.append(CheckResult(rule["id"], "CRITICAL", False,
                                           f"pack rule could not be evaluated on {line}: {e}"))
                    continue
                if fired:
                    out.append(CheckResult(rule["id"], rule["severity"], False,
                                           _render(rule["message"], {"line": line, **ctx})))
    return out
