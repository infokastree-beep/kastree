"""Note inclusion engine + FA movement grid.
v5.1: reads includeWhen (and legacy include_when); FA grid disposals now also
reduce accumulated depreciation (disposals_dep) — a disposal no longer
overstates NBV. (Review findings, both confirmed by execution.)"""
from decimal import Decimal as Dec
from .predicates import Unanswered, evaluate
from .money import money
from . import lines as L

def select_notes(templates: dict, ctx: dict) -> dict:
    """Notes to include. A note whose condition needs an unanswered disclosure
    fact is INCLUDED (pending) — never silently dropped."""
    out = {}
    for code, t in templates.items():
        inc = t.get("includeWhen") or t.get("include_when")
        if not inc:
            raise ValueError(f"template {code} has no includeWhen")
        try:
            if inc == "always" or evaluate(inc, ctx):
                out[code] = t
        except Unanswered:
            out[code] = t
    return out

def build_fa_grid(fa_register: dict) -> dict:
    """fa_register per class: opening_cost, additions, disposals (cost),
    disposals_dep (depreciation carried away), opening_dep, charge."""
    grid, total = [], {"oc": Dec(0), "add": Dec(0), "disp": Dec(0), "dd": Dec(0),
                       "od": Dec(0), "chg": Dec(0)}
    for cls, r in fa_register.items():
        dd = r.get("disposals_dep", Dec("0"))
        cc = money(r["opening_cost"] + r["additions"] - r["disposals"])
        cd = money(r["opening_dep"] + r["charge"] - dd)
        nbv_c, nbv_o = money(cc - cd), money(r["opening_cost"] - r["opening_dep"])
        grid.append({"class": cls, "opening_cost": r["opening_cost"],
                     "additions": r["additions"], "disposals": r["disposals"],
                     "disposals_dep": dd, "closing_cost": cc,
                     "opening_dep": r["opening_dep"], "charge": r["charge"],
                     "closing_dep": cd, "nbv_close": nbv_c, "nbv_open": nbv_o})
        for k, key in (("oc","opening_cost"),("add","additions"),("disp","disposals"),
                       ("dd","disposals_dep"),("od","opening_dep"),("chg","charge")):
            total[k] += money(r.get(key, Dec("0")) if key != "disposals_dep" else dd)
    tcc = money(total["oc"] + total["add"] - total["disp"])
    tcd = money(total["od"] + total["chg"] - total["dd"])
    grid.append({"class": "Total", "opening_cost": total["oc"], "additions": total["add"],
                 "disposals": total["disp"], "disposals_dep": total["dd"],
                 "closing_cost": tcc, "opening_dep": total["od"], "charge": total["chg"],
                 "closing_dep": tcd, "nbv_close": money(tcc - tcd),
                 "nbv_open": money(total["oc"] - total["od"])})
    grid.append({"invariant_holds": money(grid[-1]["nbv_open"] + total["add"]
                                          - total["chg"] - total["disp"] + total["dd"])
                          == grid[-1]["nbv_close"]})
    return grid


import re as _re

# Facts the engine DERIVES from the trial balance. Never user-overridable.
DERIVED = frozenset({"FIXED_ASSETS_NBV", "DEBTORS", "CREDITORS", "LOANS", "STOCKS",
                     "INTANGIBLE_ASSETS", "HAS_BORROWINGS", "HAS_LEASES", "REVENUE",
                     "DIRECTOR_LOANS", "DIVIDENDS_PAID"})

# Facts only the preparer can supply (the disclosure questionnaire). Tri-state:
# True/False/amount when answered, None when not yet answered. An unanswered
# fact is NEVER treated as "no": a note that needs it is included as pending,
# and check_disclosure_answers() blocks FINAL until it is answered.
ANSWER_FLAGS = frozenset({
    "GOODWILL", "DEV_COSTS", "DEV_COSTS_UNREALISED", "REVALUATION_RESERVE", "REVAL_TRANSFER",
    "CAPITALISED_BORROWING", "IMPAIRMENT", "IMPAIRMENT_REVERSAL", "FI_FVPL", "NONFI_FV",
    "FV_VS_HC_DIFFERS", "FV_DESIGNATION", "SECURED_CREDITORS", "GUARANTEES_EXIST",
    "UNCOMMITTED", "PENSION_COMMITMENT", "PAST_DIRECTOR_PENSION_COMMITMENTS",
    "OFF_BALANCE_ARRANGEMENT", "REQUIRED_BY_FORMAT", "HAS_EMPLOYEES", "DIRECTORS_EXIST",
    "PAST_DIRECTOR_BENEFITS", "THIRD_PARTY_DIRECTOR_SERVICES", "CONNECTED_LOANS",
    "DIRECTOR_LOAN_AGREEMENTS", "DIRECTOR_GUARANTEES", "DIRECTOR_GUARANTEE_AGREEMENTS",
    "DIRECTOR_MATERIAL_INTEREST", "SMALL_GROUP_EXEMPTION", "RPT_EXISTS", "OWN_SHARES_HELD",
    "IS_SUBSIDIARY", "CHARGES_EXIST", "SUBSEQUENT_EVENTS", "FORMAT_COMBINED", "SET_OFF_USED",
    "COMMITMENTS_EXIST", "FORMAT_CHANGE", "POLICY_CHANGE", "PRIOR_RECLASS",
    "GOING_CONCERN_DEPARTURE", "MULTI_ITEM_ASSET", "HAS_FOREIGN"})


def _conditions(node):
    """Every includeWhen string in a template, including nested table analyses."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "includeWhen" and isinstance(v, str):
                yield v
            else:
                yield from _conditions(v)
    elif isinstance(node, list):
        for v in node:
            yield from _conditions(v)


_NAME = _re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
_KEYWORDS = {"AND", "OR", "NOT", "TRUE", "FALSE"}


def build_note_context(mapped: dict, templates: dict, flags: dict | None = None) -> dict:
    """Disclosure context: DERIVED facts from the canonical balances (and their
    lineage), plus the preparer's ANSWER_FLAGS — None until answered."""
    m = mapped
    def g(k): return m.get(k, Dec("0"))
    def grp(lines): return sum((g(k) for k in sorted(lines)), Dec("0"))
    sources = getattr(mapped, "sources", None)
    if sources is None:
        director_loans = None  # no lineage supplied: unknown, never assumed zero
    else:  # debit balances on accounts MAPPED as director's loans, before re-homing
        director_loans = sum((s.balance for srcs in sources.values() for s in srcs
                              if s.source_line == "DIRECTOR_LOAN" and s.balance > 0), Dec("0"))
    loans = -grp(L.BORROWINGS)
    computed: dict = {
        "FIXED_ASSETS_NBV": grp(L.FIXED_ASSETS), "DEBTORS": grp(L.DEBTORS),
        "CREDITORS": -grp(L.CREDITORS_ALL), "LOANS": loans, "STOCKS": grp(L.STOCKS),
        "INTANGIBLE_ASSETS": grp(L.INTANGIBLE), "HAS_BORROWINGS": loans != 0,
        "HAS_LEASES": any(g(k) != 0 for k in sorted(L.LEASES)),
        "REVENUE": -g("REVENUE"), "DIRECTOR_LOANS": director_loans,
        "DIVIDENDS_PAID": g("DIVIDENDS"),
    }
    computed.update({name: None for name in ANSWER_FLAGS})
    if flags:
        clash = DERIVED & flags.keys()
        if clash:
            raise ValueError(f"flags may not override derived figures: {sorted(clash)}")
        unknown_flags = set(flags) - ANSWER_FLAGS
        if unknown_flags:
            raise ValueError(f"unknown disclosure answer name(s): {sorted(unknown_flags)}")
        computed.update(flags)
    used = set()
    for t in templates.values():
        for cond in _conditions(t):
            used |= set(_NAME.findall(cond))
    unknown = used - _KEYWORDS - set(computed)
    if unknown:  # a typo in a pack includeWhen must RAISE, never hide a statutory note
        raise KeyError(f"undeclared predicate name(s) in pack templates: {sorted(unknown)}")
    return computed


def check_disclosure_answers(ctx: dict, templates: dict, checklist_items: list):
    """V-DISC-001 (CRITICAL, blocks FINAL): every disclosure question that an
    APPLICABLE note or checklist item depends on must be answered."""
    from .reconciliation import CheckResult
    missing: set = set()
    conds = [c for t in templates.values() for c in _conditions(t)]
    conds += [i["includeWhen"] for i in checklist_items if i.get("includeWhen")]
    for cond in conds:
        if cond == "always":
            continue
        probe = dict(ctx)
        while True:  # collect every unanswered name this condition actually needs
            try:
                evaluate(cond, probe)
                break
            except Unanswered as e:
                missing.add(e.name)
                probe[e.name] = False  # keep probing the rest of the expression
    if missing:
        return CheckResult("V-DISC-001", "CRITICAL", False,
                           f"Unanswered disclosure questions: {sorted(missing)}")
    return None
