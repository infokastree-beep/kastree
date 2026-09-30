"""4-tier account-mapping confidence engine.
Tiers: prior-year exact=100 | prior-year code=60 | keyword=score | code-range=20.
Multi-signal boost +15 when keyword and code range AGREE.
STRUCTURAL SAFEGUARD (v4.4→5.1): heuristic scores capped below PRE_SELECT —
AUTO_CONFIRM is reachable ONLY via a prior-year exact match that was itself
human-confirmed.
v5.1 remediation: keyword matching is WORD-BOUNDARY (regex), longest keys first —
substring matching ("sales" inside "cost of sales", "rent" inside "current") is gone.
"""
from typing import NamedTuple

from . import lines as L
import re as _re
from decimal import Decimal as Dec

PRIOR_EXACT, PRIOR_CODE, MULTI_BOOST = 100, 60, 15
THRESHOLDS = {"auto_confirm": 100, "pre_select": 80, "active_choice": 50}
BALANCE_SHEET_LINES = L.BALANCE_SHEET | frozenset(L.SIGN_HOMES) | frozenset({"LOANS"})

def _keyword_score(name: str, keyword_scores: dict,
                   excluded: frozenset = frozenset()) -> tuple:
    """Best word-boundary keyword match, ignoring candidate lines in
    `excluded` so a lower-scoring valid keyword can still win."""
    n = " " + name.lower().strip() + " "
    best = (0, None)
    for kw, (line, score) in sorted(keyword_scores.items(),
                                    key=lambda kv: -len(kv[0])):
        if line in excluded or score <= best[0]:
            continue
        if _re.search(r"\b" + _re.escape(kw.lower()) + r"\b", n):
            best = (score, line)
    return best

def _code_range_score(code: str, code_ranges: dict) -> tuple:
    try: c = int(code)
    except ValueError: return (0, None)
    for (lo, hi), line in code_ranges.items():
        if lo <= c <= hi: return (20, line)
    return (0, None)

def suggest_mapping(line, prior_mappings: dict, keyword_scores: dict,
                    code_ranges: dict) -> tuple:
    prior = prior_mappings.get(line.nominal_code)
    if prior and prior.get("confirmed"):
        if prior["name"].strip().lower() == line.account_name.strip().lower():
            return prior["line"], PRIOR_EXACT, "RULE", ["prior_exact"]
        return prior["line"], PRIOR_CODE, "RULE", ["prior_code"]
    lname = line.account_name.lower()
    excluded: set = set()
    # v5.5 exclusion + review: liability-type or director names never CASH
    if _re.search(r"\b(loans?|borrowings?|mortgages?|overdrafts?|directors?'?s?|"
                  r"hire purchase|finance lease|credit card)\b", lname):
        excluded.add("CASH")
    # v7.6 stress finding: tax-term names must not fall back to CASH either
    if _re.search(r"\b(vat|paye|prsi|usc|corporation tax|income tax)\b", lname):
        excluded.add("CASH")
    # P&L wording never yields a balance-sheet suggestion via bank/motor/loan
    if _re.search(r"\b(charges?|expenses?|interest|discounts?|fees?|"
                  r"hire(?! purchase)|repairs?|running|commissions?|written off)\b", lname):
        excluded |= BALANCE_SHEET_LINES
    kw_score, kw_line = _keyword_score(line.account_name, keyword_scores,
                                       frozenset(excluded))
    rg_score, rg_line = _code_range_score(line.nominal_code, code_ranges)
    if rg_line in excluded:
        rg_score, rg_line = 0, None
    signals = []
    if kw_score: signals.append(("keyword", kw_score, kw_line))
    if rg_score: signals.append(("code_range", rg_score, rg_line))
    if not signals: return None, 0, "AUTO", []
    lines = {l for _, _, l in signals}
    best_line = max(signals, key=lambda s: s[1])[2]
    best_score = max(s[1] for s in signals)
    if len(lines) == 1 and len(signals) > 1:
        best_score = min(100, best_score + MULTI_BOOST)
    best_score = min(best_score, THRESHOLDS["pre_select"] - 1)  # safeguard
    return best_line, best_score, "AUTO", [s[0] for s in signals]

def classification(score: int) -> str:
    if score >= THRESHOLDS["auto_confirm"]: return "AUTO_CONFIRM"
    if score >= THRESHOLDS["pre_select"]:   return "PRE_SELECT"
    if score >= THRESHOLDS["active_choice"]: return "ACTIVE_CHOICE"
    return "UNKNOWN"

# Asset lines whose individual accounts must be re-presented as liabilities
# when in credit (Sch 3A: no set-off of assets against liabilities).


# v6.8 SIGN HOMES (review finding): per-canonical-line debit/credit homes,
# applied per ACCOUNT before summing, so accounts never net against each
# other and contrary-sign balances present on the correct side.
SIGN_HOMES = L.SIGN_HOMES

class Source(NamedTuple):
    """One TB account's contribution to a canonical line (lineage)."""
    nominal_code: str
    account_name: str
    source_line: str      # the line it was MAPPED to, before any sign-home re-homing
    balance: Dec


class Aggregated(dict):
    """canonical line -> balance (a plain dict for every existing caller),
    plus `sources`: canonical line -> the TB accounts that make it up.
    Lineage survives sign-home re-homing, so e.g. an overdrawn director's
    loan presented within Other debtors is still known to be a director's loan."""

    def __init__(self) -> None:
        super().__init__()
        self.sources: dict[str, list[Source]] = {}


def aggregate(tb_lines, mappings: dict) -> Aggregated:
    """Sum mapped TB balances per canonical line (debit-positive),
    applying per-account sign-home reclassification first."""
    out = Aggregated()
    for ln in tb_lines:
        src = mappings.get(ln.nominal_code)
        if src is None:
            continue
        m = src
        homes = SIGN_HOMES.get(m)
        if homes is not None:
            m = homes[0] if ln.balance >= 0 else homes[1]
        out[m] = out.get(m, Dec("0.00")) + ln.balance
        out.sources.setdefault(m, []).append(
            Source(ln.nominal_code, ln.account_name, src, ln.balance))
    return out
