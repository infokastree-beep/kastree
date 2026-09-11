# Adversarial stress v2 (2026-09-11)

**Production upload:** blocked — `CLERK_SECRET_KEY` / `CLERK_PUBLISHABLE_KEY` not in agent env.
Prod health `200`; `/trial-balances/convert-gl` without token → `401 Missing bearer token`.

**Executed against:** local ASGI HTTP API (same FastAPI routes as Railway) + service layer.
Fixtures: `fixtures/adversarial-stress-v2/` · Evidence: `results.json`

| # | Case | Verdict |
|---|------|---------|
| 1a | Mixed ISO Currency column (EUR+USD+GBP) TB | **GAP / likely bug** — parser + `/upload` accept; parse+map complete under company EUR |
| 1b | Same account code in two currencies | **GAP / likely bug** — both EUR and USD rows kept |
| 1c | Mixed €/£ symbols in GL amounts | **BUG** — `/convert-gl` accepts and strips symbols; TB path correctly raises `AmbiguousCurrencyError` |
| 2 | Exact + near-duplicate + triple GL lines | **As designed + gap** — summed correctly; no duplicate-review warning |
| 3 | Holding/group TB (investments, IC, NCI, goodwill, FCTR) | **Gap + heuristic bugs** — most group accounts correctly unmapped; `code_range` wrongly maps impairments→COS, interest receivable→interest_expense, share of associate→revenue |
| 4 | Apr–Mar FY with boundary dates | **As designed + gap** — Custom `2025-04-01`…`2026-03-31` includes 12 / excludes 6; sales `53000`; Full year preset is calendar Jan–Dec only |
| 5a | Truncated / HTML / noise xlsx | **As designed** — clear ParseError |
| 5b | Empty xlsx/csv/pdf | **As designed** (empty csv surfaces raw pandas text) |
| 5c | Password PDF | **As designed** — rejects; message does not say “password” (underlying `PDFPasswordIncorrect`) |
| 5e | Headers-only CSV | **BUG** — `/upload` 202 → parse+map complete with `mappings: []` |

Clerk secrets were requested via environment setup actions so production re-upload can proceed when available.
