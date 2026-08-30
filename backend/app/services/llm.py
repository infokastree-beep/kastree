"""LLM prompt templates and helpers.

Prompt version: mapping-tie-breaker-v1
"""

from __future__ import annotations

# Prompt version: mapping-tie-breaker-v1
# Source: .cursorrules Section 7.2 — use verbatim; do not rewrite.
MAPPING_TIE_BREAKER_SYSTEM = """You are an accounting assistant. Map each account to exactly one canonical category.
Available: revenue, cost_of_sales, operating_expenses, depreciation, interest_income, interest_expense,
tax, property_plant_equipment, intangible_assets, inventory, trade_receivables, cash,
trade_payables, accruals, loans, share_capital, retained_earnings, dividends, unmapped.
Respond JSON: {"mappings": [{"index": 1, "canonical_line": "...", "reasoning": "..."}]}
Rules: No monetary amounts. Conservative. Use "unmapped" if unclear."""

# Canonical lines the mapping tie-breaker prompt permits (Appendix A mappable set + unmapped).
MAPPING_TIE_BREAKER_CANONICAL_LINES: frozenset[str] = frozenset(
    {
        "revenue",
        "cost_of_sales",
        "operating_expenses",
        "depreciation",
        "interest_income",
        "interest_expense",
        "tax",
        "property_plant_equipment",
        "intangible_assets",
        "inventory",
        "trade_receivables",
        "cash",
        "trade_payables",
        "accruals",
        "loans",
        "share_capital",
        "retained_earnings",
        "dividends",
        "unmapped",
    }
)
