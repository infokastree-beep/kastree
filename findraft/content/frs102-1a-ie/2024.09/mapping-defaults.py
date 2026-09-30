"""Default account-mapping library. v5.1 remediation:
- Keywords are WORD-BOUNDARY matched (engine/mapping.py), longest keys first;
  dangerous substrings removed/reshaped ("sales" no longer matches "cost of
  sales"; bare "receivable" removed; interest accounts get exact phrases).
- Code ranges are a genuine Sage 50-style default (1100 debtors control,
  2100 creditors control, 4000 sales, 7000+ overheads) — the previous set
  mapped Sage's creditors control to current assets. Adjust per ledger.
"""
KEYWORD_SCORES = {
 "trade debtors": ("TRADE_DEBTORS", 40), "trade receivables": ("TRADE_DEBTORS", 40),
 "sales ledger control": ("TRADE_DEBTORS", 40), "debtors control": ("TRADE_DEBTORS", 40),
 "trade creditors": ("TRADE_CREDITORS", 40), "trade payables": ("TRADE_CREDITORS", 40),
 "purchase ledger control": ("TRADE_CREDITORS", 40), "creditors control": ("TRADE_CREDITORS", 40),
 "cost of sales": ("COST_OF_SALES", 45), "materials": ("COST_OF_SALES", 30),
 "sales revenue": ("REVENUE", 40), "turnover": ("REVENUE", 35), "sales": ("REVENUE", 30),
 "bank current account": ("CASH", 40), "current account": ("CASH", 35),
 "cash at bank": ("CASH", 40), "cash": ("CASH", 25),
 # real-world abbreviations (review finding: "Bank - Current a/c" went unmapped)
 "bank a/c": ("CASH", 40), "current a/c": ("CASH", 40), "curr a/c": ("CASH", 40),
 "bank acc": ("CASH", 40), "cash a/c": ("CASH", 40),
 # bare "bank" stays LOW: any specific phrase above outranks it, and the
 # exclusion rule in suggest_mapping drops CASH for loan-type names
 "bank": ("CASH", 15),
 "fixtures and fittings": ("FA_FIXTURES_COST", 40), "fixtures": ("FA_FIXTURES_COST", 35),
 "fittings": ("FA_FIXTURES_COST", 35),
 "land and buildings": ("FA_LAND_BUILDINGS", 40), "land": ("FA_LAND_BUILDINGS", 30),
 "buildings": ("FA_LAND_BUILDINGS", 30),
 "investments": ("FA_INVESTMENTS", 35), "investment property": ("FA_INVESTMENTS", 35),
 "vat": ("VAT_CONTROL", 40), "value added tax": ("VAT_CONTROL", 40),
 "paye": ("PAYE_PRSI", 40), "prsi": ("PAYE_PRSI", 40), "usc": ("PAYE_PRSI", 35),
 "director's loan": ("DIRECTOR_LOAN", 40), "directors loan": ("DIRECTOR_LOAN", 40),
 "director loan": ("DIRECTOR_LOAN", 40), "director current account": ("DIRECTOR_LOAN", 40),
 "directors current account": ("DIRECTOR_LOAN", 40),
 "share premium": ("SHARE_PREMIUM", 40), "provisions": ("PROVISIONS", 40),
 "deferred tax": ("DEFERRED_TAX", 40), "accrued income": ("ACCRUED_INCOME", 40),
 "deferred income": ("DEFERRED_INCOME", 40), "capital grants": ("DEFERRED_INCOME", 35),
 # must be presentable lines (the consumed-lines assertion refuses "LOANS")
 "hire purchase": ("LOANS_GT1Y", 35), "finance lease": ("LEASE_LIABILITY_GT1Y", 35),
 "bank loan": ("LOANS_GT1Y", 40), "bank borrowings": ("LOANS_GT1Y", 40),
 # "LOANS" is not a presentable line; default long-term, split <1y/>1y at review
 "loan": ("LOANS_GT1Y", 30), "borrowings": ("LOANS_GT1Y", 30), "overdraft": ("LOANS_LT1Y", 40),
 "interest receivable": ("INTEREST_RECEIVABLE", 40), "interest payable": ("INTEREST_PAYABLE", 40),
 "loan interest": ("INTEREST_PAYABLE", 40), "interest": ("INTEREST_PAYABLE", 25),
 "bank charges": ("ADMIN_EXPENSES", 40), "motor expenses": ("ADMIN_EXPENSES", 40),
 "depreciation charge": ("DEPRECIATION_CHARGE", 40), "depreciation": ("DEPRECIATION_CHARGE", 30),
 "accumulated depreciation": ("FA_ACCUM_DEP", 40),
 # canonical lines MUST be ones engine/statements.py presents (CONSUMED_LINES)
 "rent": ("ADMIN_EXPENSES", 30),
 "salaries": ("ADMIN_EXPENSES", 35), "wages": ("ADMIN_EXPENSES", 35),
 "payroll": ("ADMIN_EXPENSES", 35), "stock": ("STOCKS", 35), "stocks": ("STOCKS", 35),
 "plant": ("FA_PLANT_COST", 30), "machinery": ("FA_PLANT_COST", 30),
 "equipment": ("FA_PLANT_COST", 30), "computer equipment": ("FA_PLANT_COST", 30),
 "motor vehicles": ("FA_MOTOR_COST", 40), "motor": ("FA_MOTOR_COST", 30),
 "vehicles": ("FA_MOTOR_COST", 30),
 "share capital": ("SHARE_CAPITAL", 40), "ordinary shares": ("SHARE_CAPITAL", 40),
 "retained earnings": ("RETAINED_EARNINGS", 40), "p&l reserve": ("RETAINED_EARNINGS", 40),
 "dividends": ("DIVIDENDS", 40),
}
CODE_RANGES = {  # Sage 50-style default
 (10, 49): "FA_PLANT_COST", (50, 59): "FA_MOTOR_COST",   # Sage 0010-0059
 (1000, 1099): "STOCKS", (1100, 1109): "TRADE_DEBTORS",
 (1200, 1299): "CASH", (2100, 2109): "TRADE_CREDITORS",
 (2200, 2299): "OTHER_CREDITORS", (2300, 2399): "LOANS_LT1Y",
 (3000, 3009): "SHARE_CAPITAL", (3100, 3109): "RETAINED_EARNINGS",
 (3200, 3299): "RETAINED_EARNINGS",
 (4000, 4099): "REVENUE", (5000, 5999): "COST_OF_SALES",
 (6000, 6999): "COST_OF_SALES",  # Sage 6xxx = direct expenses
 (7000, 7999): "ADMIN_EXPENSES", (8000, 8999): "ADMIN_EXPENSES",
}
PRIOR_YEAR_EXACT = 100
PRIOR_YEAR_CODE = 60
MULTI_SIGNAL_BOOST = 15
THRESHOLDS = {"auto_confirm": 100, "pre_select": 80, "active_choice": 50}
