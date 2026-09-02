"""LLM prompt templates and helpers.

Prompt versions: mapping-tie-breaker-v1, variance-commentary-v1, business-health-v1
"""

from __future__ import annotations

# Prompt version: mapping-tie-breaker-v1
# Source: .cursorrules Section 7.2 — use verbatim; do not rewrite.
MAPPING_TIE_BREAKER_SYSTEM = """You are an accounting assistant. Map each account to exactly one canonical category.
Available: revenue, cost_of_sales, operating_expenses, depreciation, interest_income, interest_expense,
tax, property_plant_equipment, intangible_assets, investments, inventory, trade_receivables,
prepayments_and_accrued_income, cash, trade_payables, provisions, accruals_and_deferred_income,
taxation_and_social_security, loans, share_capital, share_premium, retained_earnings,
revaluation_reserve, dividends, unmapped.
Respond JSON: {"mappings": [{"index": 1, "canonical_line": "...", "reasoning": "..."}]}
Rules: No monetary amounts. Conservative. Use "unmapped" if unclear."""

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
        "interest_income",
        "interest_expense",
        "tax",
        "property_plant_equipment",
        "intangible_assets",
        "investments",
        "inventory",
        "trade_receivables",
        "prepayments_and_accrued_income",
        "cash",
        "trade_payables",
        "provisions",
        "accruals_and_deferred_income",
        "taxation_and_social_security",
        "loans",
        "share_capital",
        "share_premium",
        "retained_earnings",
        "revaluation_reserve",
        "dividends",
        "unmapped",
    }
)
