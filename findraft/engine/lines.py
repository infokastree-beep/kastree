"""ONE registry of canonical lines and the statement groups they belong to.

Every sum in the engine iterates these groups — the statements, the notes
context, the review rules and the mapping exclusions — so a line can never
be counted in one place and forgotten in another (the bug class behind the
v6.8/v6.9 fixes and the lease-creditors note gap found in the v7.4 review).
"""
from typing import Final

# --- statement of financial position (debit-positive balances) ---
TANGIBLE: Final = frozenset({"FA_PLANT_COST", "FA_MOTOR_COST", "FA_FIXTURES_COST",
                             "FA_LAND_BUILDINGS", "FA_ACCUM_DEP"})
INTANGIBLE: Final = frozenset({"FA_INTANGIBLE_COST", "FA_INTANGIBLE_AMORT"})
FA_INVESTMENTS: Final = frozenset({"FA_INVESTMENTS"})
ROU: Final = frozenset({"ROU_ASSETS"})
STOCKS: Final = frozenset({"STOCKS"})
TRADE_DEBTORS: Final = frozenset({"TRADE_DEBTORS"})
OTHER_DEBTORS: Final = frozenset({"OTHER_DEBTORS", "PREPAYMENTS", "VAT_ASSET", "PAYE_ASSET",
                                  "ACCRUED_INCOME", "DEFERRED_TAX_ASSET"})
CASH: Final = frozenset({"CASH"})
CREDITORS_LT1Y: Final = frozenset({"TRADE_CREDITORS", "OTHER_CREDITORS", "ACCRUALS", "CORP_TAX",
                                   "VAT_CREDITOR", "PAYE_PRSI_CREDITOR", "DEFERRED_INCOME",
                                   "BANK_OVERDRAFT", "LOANS_LT1Y", "LEASE_LIABILITY_LT1Y"})
LOANS_GT1Y: Final = frozenset({"LOANS_GT1Y"})
LEASE_GT1Y: Final = frozenset({"LEASE_LIABILITY_GT1Y"})
PROVISIONS: Final = frozenset({"PROVISIONS"})
DEFERRED_TAX_LIABILITY: Final = frozenset({"DEFERRED_TAX_LIABILITY"})
SHARE_CAPITAL: Final = frozenset({"SHARE_CAPITAL"})
SHARE_PREMIUM: Final = frozenset({"SHARE_PREMIUM"})
RETAINED_EARNINGS: Final = frozenset({"RETAINED_EARNINGS"})

FIXED_ASSETS: Final = TANGIBLE | INTANGIBLE | FA_INVESTMENTS
DEBTORS: Final = TRADE_DEBTORS | OTHER_DEBTORS
CREDITORS_ALL: Final = CREDITORS_LT1Y | LOANS_GT1Y | LEASE_GT1Y
BORROWINGS: Final = frozenset({"LOANS_LT1Y", "LOANS_GT1Y"})
LEASES: Final = frozenset({"ROU_ASSETS", "LEASE_LIABILITY_LT1Y", "LEASE_LIABILITY_GT1Y"})
BALANCE_SHEET: Final = (FIXED_ASSETS | ROU | STOCKS | DEBTORS | CASH | CREDITORS_ALL | PROVISIONS
                        | DEFERRED_TAX_LIABILITY | SHARE_CAPITAL | SHARE_PREMIUM | RETAINED_EARNINGS)

# --- income statement ---
EXPENSES: Final = frozenset({"COST_OF_SALES", "DISTRIBUTION_COSTS", "ADMIN_EXPENSES",
                             "DEPRECIATION_CHARGE", "INTEREST_PAYABLE", "TAX_CHARGE"})
INCOME: Final = frozenset({"REVENUE", "OTHER_OPERATING_INCOME", "INTEREST_RECEIVABLE"})
EQUITY_MOVEMENTS: Final = frozenset({"DIVIDENDS"})
INCOME_STATEMENT: Final = EXPENSES | INCOME

# Every line some statement presents; anything else non-zero is refused.
CONSUMED: Final = BALANCE_SHEET | INCOME_STATEMENT | EQUITY_MOVEMENTS

# Mapping-only source lines, re-homed per account by sign before summing.
SIGN_HOMES: Final = {
    "CASH": ("CASH", "BANK_OVERDRAFT"),
    "DIRECTOR_LOAN": ("OTHER_DEBTORS", "OTHER_CREDITORS"),
    "VAT_CONTROL": ("VAT_ASSET", "VAT_CREDITOR"),
    "PAYE_PRSI": ("PAYE_ASSET", "PAYE_PRSI_CREDITOR"),
    "DEFERRED_TAX": ("DEFERRED_TAX_ASSET", "DEFERRED_TAX_LIABILITY"),
}
