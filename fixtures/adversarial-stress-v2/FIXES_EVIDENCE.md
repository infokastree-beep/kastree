# Stress bug fixes evidence (2026-09-11)

## 1. Headers-only CSV — REJECTED
Fixture: `fixtures/adversarial-stress-v2/05e_headers_only.csv`
- Direct parse: ParseError "No trial balance data rows found..."
- HTTP `/upload` → TB status `failed` with same message (no longer silent empty mappings)

## 2. Mixed €/£ GL — AmbiguousCurrencyError
Fixture: `fixtures/adversarial-stress-v2/01c_mixed_symbol_gl.xlsx`
- `convert_gl_file_to_tb` raises AmbiguousCurrencyError {£, €}
- HTTP `/convert-gl` → 422 `AMBIGUOUS_CURRENCY`
- Regression: single-€ GL still converts; TB mixed symbols still rejected

## 3. Mapper Tier 3 fallthrough
Fixture: `fixtures/adversarial-stress-v2/03_holding_company_group_structure_tb.xlsx`
- Impairment / goodwill write-down → unmapped (was cost_of_sales)
- Interest receivable → unmapped (was interest_expense)
- Share of associate profit → unmapped (was revenue)
- Controls still map: management charge→revenue, admin→opex, interest payable→interest_expense

Full JSON: evidence.json
