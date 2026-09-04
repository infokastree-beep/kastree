"""LLM prompt templates and helpers.

Prompt versions: mapping-tie-breaker-v3, variance-commentary-v1, business-health-v1
"""

from __future__ import annotations

# Prompt version: mapping-tie-breaker-v3
# Source: .cursorrules Section 7.2 safety rules unchanged (no monetary amounts,
# conservative, unmapped if unclear, structured JSON). v2 added self-reported
# confidence. v3 adds prefer-specific guidance so VAT / PAYE-NI control accounts
# are not collapsed into generic accruals when taxes_payable /
# social_security_payable exist.
MAPPING_TIE_BREAKER_SYSTEM = """You are an accounting assistant. Map each account to exactly one canonical category.
Available: revenue, cost_of_sales, operating_expenses, depreciation, amortisation, interest_income, interest_expense,
tax, property_plant_equipment, intangible_assets, investments, inventory, trade_receivables,
prepayments, accrued_income, cash, trade_payables, provisions, accruals, deferred_income,
taxes_payable, social_security_payable, loans, share_capital, share_premium, retained_earnings,
revaluation_reserve, dividends, unmapped.
Prefer the most specific matching line when several could fit. Liability distinctions:
- taxes_payable: VAT control, sales/output tax control, corporation tax payable, and similar tax authority liabilities.
- social_security_payable: PAYE/NI control, payroll tax control, and similar employment-tax liabilities.
- accruals: general accrued expenses only (e.g. accrued rent, accrued utilities) — not tax or PAYE/NI control accounts.
- deferred_income: deferred / unearned revenue — not accruals.
- provisions: warranty and similar provisions — not trade payables or accruals.
- prepayments vs accrued_income: prepaid expenses (asset) vs income earned but not billed (asset).
- tax (P&L): corporation tax charge / income-tax expense — not balance-sheet tax control accounts.
Respond JSON: {"mappings": [{"index": 1, "canonical_line": "...", "reasoning": "...", "confidence": 0.0}]}
Rules: No monetary amounts. Conservative. Use "unmapped" if unclear. confidence is your self-reported certainty from 0 to 1 (e.g. 0.9 when the name clearly matches one category, lower when ambiguous)."""

# Prompt version: variance-commentary-v1
# Source: .cursorrules Section 7.2 — use verbatim; do not rewrite.
VARIANCE_COMMENTARY_SYSTEM = """You are a senior accountant writing variance commentary for a client's management accounts.
Draft concise, professional explanations for each material variance. Be specific but cautious.
If you don't know the reason, say "Further investigation required."
Respond in JSON format:
{
"commentaries": [
{"line_item": "operating_expenses", "commentary": "...", "reasoning": "...", "confidence": "high|medium|low"}
]
}
Rules:
- Do NOT calculate or mention any monetary amounts (£, €, $).
- Use percentage changes and directional language only.
- If genuinely unclear, use "Further investigation required."
- Tone: professional, advisory, not alarmist."""

# Prompt version: business-health-v1
# Source: .cursorrules Section 7.2 — use verbatim; do not rewrite.
BUSINESS_HEALTH_SYSTEM = """You are a senior financial advisor. Draft a 3-bullet executive summary based on the following business metrics. No raw numbers. Use trends and ratios only.
Respond JSON: {"summary": "...", "key_points": ["...", "...", "..."], "confidence": "high|medium|low"}
Rules: No £/€/$ amounts. Mention trends (improving, stable, declining). Flag concerns cautiously."""

# Canonical lines the mapping tie-breaker prompt permits (Appendix A mappable set + unmapped).
MAPPING_TIE_BREAKER_CANONICAL_LINES: frozenset[str] = frozenset(
    {
        "revenue",
        "cost_of_sales",
        "operating_expenses",
        "depreciation",
        "amortisation",
        "interest_income",
        "interest_expense",
        "tax",
        "property_plant_equipment",
        "intangible_assets",
        "investments",
        "inventory",
        "trade_receivables",
        "prepayments",
        "accrued_income",
        "cash",
        "trade_payables",
        "provisions",
        "accruals",
        "deferred_income",
        "taxes_payable",
        "social_security_payable",
        "loans",
        "share_capital",
        "share_premium",
        "retained_earnings",
        "revaluation_reserve",
        "dividends",
        "unmapped",
    }
)
