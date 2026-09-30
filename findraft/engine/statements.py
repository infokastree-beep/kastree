"""Statement builders — consume the mapping engine's canonical output.
v5.1 remediation (review-confirmed flaws fixed):
- NO hard-coded nominal codes: every figure derives from `mapped`
  (canonical_line -> balance, debit-positive), the same dictionary the
  mapping engine produces. Lineage flows from mapping -> aggregation -> figure.
- Income statement follows the statutory function-of-expense format:
  distribution costs before administrative expenses; NO separate
  "Depreciation charge" face line (depreciation is disclosed in the notes
  per 1AD.14); administrative expenses INCLUDE the depreciation charge.
- Emits TOTAL_ASSETS and TOTAL_LIABILITIES_AND_EQUITY so the balance check
  consumes real figures (the old keys compared 0 to 0 and always passed).
Compliance statement (1A.6A) is engine-side text pending pack extraction —
recorded as known limitation in the remediation log.
"""
from decimal import Decimal as Dec
from .money import money
from . import lines as L

def _m(mapped: dict, key: str) -> Dec:
    return mapped.get(key, Dec("0.00"))

CONSUMED_LINES = L.CONSUMED


def _assert_all_consumed(mapped: dict) -> None:
    stray = {k for k, v in mapped.items() if k not in CONSUMED_LINES and v != 0}
    if stray:  # never silently drop money
        raise ValueError(f"canonical lines not presented by any statement: {sorted(stray)}")


SOFP_COMPLIANCE_STATEMENT = ("These financial statements have been prepared in accordance with the "
                             "provisions applicable to companies subject to the small companies regime.")


def build_sofp(mapped: dict, prior: dict) -> dict:
    """mapped: canonical_line -> balance (debit-positive; liabilities/equity
    credits negative). prior: validated prior-year figures, same sign
    convention (creditors stored negative)."""
    _assert_all_consumed(mapped)
    def grp(lines: frozenset) -> Dec:
        return money(sum((_m(mapped, k) for k in sorted(lines)), Dec("0.00")))
    v = {
        "TANGIBLE_ASSETS": grp(L.TANGIBLE),
        "INTANGIBLE_ASSETS": grp(L.INTANGIBLE),
        "INVESTMENTS_FA": grp(L.FA_INVESTMENTS),
        "STOCKS": grp(L.STOCKS),
        "TRADE_DEBTORS": grp(L.TRADE_DEBTORS),
        "OTHER_DEBTORS": grp(L.OTHER_DEBTORS),
        "CASH": grp(L.CASH),
        "CREDITORS_LT1Y": grp(L.CREDITORS_LT1Y),
        "LOANS_GT1Y": grp(L.LOANS_GT1Y),
        "SHARE_CAPITAL": -grp(L.SHARE_CAPITAL),
        "SHARE_PREMIUM": -grp(L.SHARE_PREMIUM),
        # liabilities below TALCL keep the raw (credit-negative) sign, like LOANS_GT1Y
        "PROVISIONS": grp(L.PROVISIONS),
        "DEFERRED_TAX_LIABILITY": grp(L.DEFERRED_TAX_LIABILITY),
        "RETAINED_EARNINGS": -grp(L.RETAINED_EARNINGS),
        "ROU_ASSETS": grp(L.ROU),
        "LEASE_LIABILITY": grp(L.LEASE_GT1Y),
    }
    profit = build_income_statement(mapped, {})["profit"]  # ONE profit definition
    v["RETAINED_EARNINGS"] = money(v["RETAINED_EARNINGS"] + profit - _m(mapped,"DIVIDENDS"))
    fixed = v["INTANGIBLE_ASSETS"] + v["TANGIBLE_ASSETS"] + v["INVESTMENTS_FA"] + v["ROU_ASSETS"]
    current_assets = v["STOCKS"] + v["TRADE_DEBTORS"] + v["OTHER_DEBTORS"] + v["CASH"]
    creditors_1y = v["CREDITORS_LT1Y"]
    nca = money(current_assets + creditors_1y)
    talcl = money(fixed + nca)
    net_assets = money(talcl + v["LEASE_LIABILITY"] + v["LOANS_GT1Y"]
                       + v["PROVISIONS"] + v["DEFERRED_TAX_LIABILITY"])
    equity = money(v["SHARE_CAPITAL"] + v["SHARE_PREMIUM"] + v["RETAINED_EARNINGS"])
    rows = [
        ("Intangible assets", v["INTANGIBLE_ASSETS"], prior.get("INTANGIBLE_ASSETS")),
        ("Tangible assets", v["TANGIBLE_ASSETS"], prior.get("TANGIBLE_ASSETS")),
        ("Fixed asset investments", v["INVESTMENTS_FA"], prior.get("INVESTMENTS_FA")),
        ("Right-of-use assets", v["ROU_ASSETS"], prior.get("ROU_ASSETS")),
        ("Stocks", v["STOCKS"], prior.get("STOCKS")),
        ("Trade debtors", v["TRADE_DEBTORS"], prior.get("TRADE_DEBTORS")),
        ("Other debtors", v["OTHER_DEBTORS"], prior.get("OTHER_DEBTORS")),
        ("Cash at bank and in hand", v["CASH"], prior.get("CASH")),
        ("Total current assets", current_assets, prior.get("TOTAL_CURRENT_ASSETS")),
        ("Creditors: amounts falling due within one year", creditors_1y, prior.get("CREDITORS_LT1Y")),
        ("Net current assets", nca, prior.get("NET_CURRENT_ASSETS")),
        ("Total assets less current liabilities", talcl, prior.get("TALCL")),
        ("Lease liabilities", v["LEASE_LIABILITY"], prior.get("LEASE_LIABILITY")),
        ("Creditors: amounts falling due after more than one year", v["LOANS_GT1Y"], prior.get("LOANS_GT1Y")),
        ("Provisions for liabilities", v["PROVISIONS"], prior.get("PROVISIONS")),
        ("Deferred tax liability", v["DEFERRED_TAX_LIABILITY"], prior.get("DEFERRED_TAX_LIABILITY")),
        ("Net assets", net_assets, prior.get("NET_ASSETS")),
        ("Called up share capital", v["SHARE_CAPITAL"], prior.get("SHARE_CAPITAL")),
        ("Share premium account", v["SHARE_PREMIUM"], prior.get("SHARE_PREMIUM")),
        ("Profit and loss account", v["RETAINED_EARNINGS"], prior.get("RETAINED_EARNINGS")),
        ("Total equity", equity, prior.get("EQUITY")),
    ]
    return {"rows": rows, "net_assets": net_assets, "equity": equity,
            "articulates": net_assets == equity,
            "TOTAL_ASSETS": money(fixed + current_assets),
            "TOTAL_LIABILITIES_AND_EQUITY": money(-creditors_1y - v["LEASE_LIABILITY"]
                                                  - v["LOANS_GT1Y"] - v["PROVISIONS"]
                                                  - v["DEFERRED_TAX_LIABILITY"] + equity),
            "profit": profit,
            # FRS 102 1A.6A: on the SoFP, prominently above the directors' signatures
            # (Ireland: s.324(4A) Companies Act 2014). Distinct from note N1's
            # statement of compliance with Section 1A (1AD.3 / s.291(7)).
            "compliance_statement": SOFP_COMPLIANCE_STATEMENT}

# Row label -> prior-dict key (and sign: -1 where the prior dict stores costs positive).
SOFP_KEYS = {
    "Intangible assets": "INTANGIBLE_ASSETS", "Tangible assets": "TANGIBLE_ASSETS",
    "Fixed asset investments": "INVESTMENTS_FA", "Right-of-use assets": "ROU_ASSETS",
    "Stocks": "STOCKS", "Trade debtors": "TRADE_DEBTORS", "Other debtors": "OTHER_DEBTORS",
    "Cash at bank and in hand": "CASH", "Total current assets": "TOTAL_CURRENT_ASSETS",
    "Creditors: amounts falling due within one year": "CREDITORS_LT1Y",
    "Net current assets": "NET_CURRENT_ASSETS", "Total assets less current liabilities": "TALCL",
    "Lease liabilities": "LEASE_LIABILITY",
    "Creditors: amounts falling due after more than one year": "LOANS_GT1Y",
    "Provisions for liabilities": "PROVISIONS", "Deferred tax liability": "DEFERRED_TAX_LIABILITY",
    "Net assets": "NET_ASSETS", "Called up share capital": "SHARE_CAPITAL",
    "Share premium account": "SHARE_PREMIUM", "Profit and loss account": "RETAINED_EARNINGS",
    "Total equity": "EQUITY"}
IS_KEYS = {
    "Turnover": ("REVENUE", 1), "Cost of sales": ("COST_OF_SALES", -1),
    "Gross profit": ("GROSS_PROFIT", 1), "Distribution costs": ("DISTRIBUTION_COSTS", -1),
    "Administrative expenses (including depreciation)": ("ADMIN_EXPENSES", -1),
    "Other operating income": ("OTHER_OPERATING_INCOME", 1),
    "Operating profit": ("OPERATING_PROFIT", 1), "Interest receivable": ("INTEREST_RECEIVABLE", 1),
    "Interest payable": ("INTEREST_PAYABLE", -1), "Profit before tax": ("PBT", 1),
    "Tax on profit": ("TAX", -1), "Profit for the financial year": ("PROFIT", 1)}


def prior_from_mapped(prior_mapped: dict) -> dict:
    """Comparatives from the prior year's CANONICAL LINE balances (the validated
    prior-year TB after mapping), rendered by the same builders as the current
    year — so every line, including chart-v2 lines, has a comparative source."""
    out: dict = {}
    for label, cur, _ in build_sofp(prior_mapped, {})["rows"]:
        out[SOFP_KEYS[label]] = cur
    for label, cur, _ in build_income_statement(prior_mapped, {})["rows"]:
        key, sign = IS_KEYS[label]
        out[key] = money(sign * cur)
    # ONE convention for every prior dict: ADMIN_EXPENSES EXCLUDES depreciation,
    # DEPRECIATION is separate, and the income statement adds them together.
    dep = money(_m(prior_mapped, "DEPRECIATION_CHARGE"))
    out["ADMIN_EXPENSES"] = money(out["ADMIN_EXPENSES"] - dep)
    out["DEPRECIATION"] = dep
    return out


def build_income_statement(mapped: dict, prior: dict) -> dict:
    turnover = money(-_m(mapped,"REVENUE"))
    cos = money(_m(mapped,"COST_OF_SALES"))
    dist = money(_m(mapped,"DISTRIBUTION_COSTS"))
    admin = money(_m(mapped,"ADMIN_EXPENSES") + _m(mapped,"DEPRECIATION_CHARGE"))
    other_inc = money(-_m(mapped,"OTHER_OPERATING_INCOME"))
    int_rec = money(-_m(mapped,"INTEREST_RECEIVABLE"))
    int_pay = money(_m(mapped,"INTEREST_PAYABLE"))
    tax = money(_m(mapped,"TAX_CHARGE"))
    gross = money(turnover - cos)
    operating = money(gross - dist - admin + other_inc)
    pbt = money(operating + int_rec - int_pay)
    profit = money(pbt - tax)
    def neg(k: str) -> Dec | None:  # prior costs stored positive -> present as current
        return None if prior.get(k) is None else -prior[k]
    prior_admin = (None if prior.get("ADMIN_EXPENSES") is None
                   else -(prior["ADMIN_EXPENSES"] + prior.get("DEPRECIATION", Dec("0"))))
    rows = [("Turnover", turnover, prior.get("REVENUE")),
            ("Cost of sales", -cos, neg("COST_OF_SALES")),
            ("Gross profit", gross, prior.get("GROSS_PROFIT")),
            ("Distribution costs", -dist, neg("DISTRIBUTION_COSTS")),
            ("Administrative expenses (including depreciation)", -admin, prior_admin),
            ("Other operating income", other_inc, prior.get("OTHER_OPERATING_INCOME")),
            ("Operating profit", operating, prior.get("OPERATING_PROFIT")),
            ("Interest receivable", int_rec, prior.get("INTEREST_RECEIVABLE")),
            ("Interest payable", -int_pay, neg("INTEREST_PAYABLE")),
            ("Profit before tax", pbt, prior.get("PBT")),
            ("Tax on profit", -tax, neg("TAX")),
            ("Profit for the financial year", profit, prior.get("PROFIT"))]
    return {"rows": rows, "profit": profit, "dividends": _m(mapped,"DIVIDENDS")}
