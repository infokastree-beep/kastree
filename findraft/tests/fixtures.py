"""Golden fixtures from the build pack §7 (v3 CORRECTED class-level FA split).
Demo Engineering Limited, IE, y/e 31 Dec 2026. All figures machine-verified.

PERIOD START (v5.2): the fixture is a 12-month period 1 Jan 2026 - 31 Dec 2026
(full-year 2025 comparatives throughout). 1 January 2026 IS "on or after
1 January 2026" — the FRS 102 Periodic Review 2024 changes (five-step revenue,
on-balance-sheet leases per the IFRS 16-aligned model) APPLY to this fixture
year, as their first effective period. This is why the RE roll-forward carries
a transition_adjustment slot (modified retrospective, cumulative effect to
opening retained earnings)."""

PERIOD = {"start": "2026-01-01", "end": "2026-12-31"}
from decimal import Decimal as Dec
from engine.schemas import TBLine

TB = [
 ("1500","Plant & machinery - cost",150000,0), ("1501","Motor vehicles - cost",60000,0),
 ("1505","Accumulated depreciation - plant",0,52000), ("1506","Accumulated depreciation - motor",0,24000),
 ("2100","Trade debtors",245800,0), ("2110","Other debtors",15400,0), ("2120","Prepayments",6200,0),
 ("2130","Bank current account",284912,0),
 ("2200","Trade creditors",0,67200), ("2210","Other creditors",0,8400), ("2220","Accruals",0,5600),
 ("2230","Corporation tax",0,14300), ("2240","Loan - due within one year",0,15000),
 ("2300","Loan - due after more than one year",0,120000),
 ("3000","Called up share capital",0,100), ("3100","Retained earnings b/f",0,322062),
 ("4000","Sales revenue",0,2421300), ("5000","Cost of sales",1579600,0),
 ("6000","Administrative expenses",611750,0), ("6100","Interest receivable",0,1200),
 ("7000","Depreciation charge",22400,0), ("7100","Interest payable",9600,0),
 ("8500","Dividends paid",24000,0), ("8600","Tax charge",41500,0),
]
def tb_lines():
    return [TBLine(c, n, Dec(str(dr)), Dec(str(cr))) for c, n, dr, cr in TB]

MAPPINGS = {  # canonical_line per code for the fixture (as a confirmed mapping set would be)
 "1500":"FA_PLANT_COST","1501":"FA_MOTOR_COST","1505":"FA_ACCUM_DEP","1506":"FA_ACCUM_DEP",
 "2100":"TRADE_DEBTORS","2110":"OTHER_DEBTORS","2120":"PREPAYMENTS","2130":"CASH",
 "2200":"TRADE_CREDITORS","2210":"OTHER_CREDITORS","2220":"ACCRUALS","2230":"CORP_TAX",
 "2240":"LOANS_LT1Y","2300":"LOANS_GT1Y","3000":"SHARE_CAPITAL","3100":"RETAINED_EARNINGS",
 "4000":"REVENUE","5000":"COST_OF_SALES","6000":"ADMIN_EXPENSES","6100":"INTEREST_RECEIVABLE",
 "7000":"DEPRECIATION_CHARGE","7100":"INTEREST_PAYABLE","8500":"DIVIDENDS","8600":"TAX_CHARGE",
}

PRIOR = {  # validated prior-year data (post-gate)
 "TANGIBLE_ASSETS": Dec("111400"), "TRADE_DEBTORS": Dec("225000"),
 "OTHER_DEBTORS": Dec("15500"), "CASH": Dec("176262"),
 "CREDITORS_LT1Y": Dec("-71000"), "NET_CURRENT_ASSETS": Dec("345762"),
 "TALCL": Dec("457162"), "LOANS_GT1Y": Dec("-135000"),
 "NET_ASSETS": Dec("322162"), "SHARE_CAPITAL": Dec("100"),
 "RETAINED_EARNINGS": Dec("322062"), "EQUITY": Dec("322162"),
 "TOTAL_CURRENT_ASSETS": Dec("416762"),
 "REVENUE": Dec("2105400"), "COST_OF_SALES": Dec("1402000"),
 "GROSS_PROFIT": Dec("703400"), "ADMIN_EXPENSES": Dec("540200"),
 "DEPRECIATION": Dec("20100"), "OPERATING_PROFIT": Dec("143100"),
 "INTEREST_RECEIVABLE": Dec("900"), "INTEREST_PAYABLE": Dec("11200"),
 "PBT": Dec("132800"), "TAX": Dec("34600"), "PROFIT": Dec("98200"),
}

# FA register: opening derived from corrected grid — closing dep FIXED by TB accounts
# 1505 (52,000) and 1506 (24,000); charge split 16,400 / 6,000.
FA_REGISTER = {
 "Plant & machinery": {"opening_cost": Dec("120000"), "additions": Dec("30000"),
   "disposals": Dec("0"), "opening_dep": Dec("35600"), "charge": Dec("16400")},
 "Motor vehicles": {"opening_cost": Dec("45000"), "additions": Dec("15000"),
   "disposals": Dec("0"), "opening_dep": Dec("18000"), "charge": Dec("6000")},
}


# The pinned pack whose review rules every test evaluates (there is no default).
import pathlib as _pathlib
RULES = _pathlib.Path(__file__).resolve().parent.parent / "content" / "frs102-1a-ie" / "2024.09" / "review-rules.json"
