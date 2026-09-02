# Canonical lines expansion

Design for expanding Appendix A's mappable canonical set, confirmed via live
testing with a complex 74-account trial balance (see
[`tracked-gaps.md`](tracked-gaps.md) — Appendix A canonical set section).

**Sequencing:** fast-follow after Variance Analysis and materiality
auto-suggestion on the [product roadmap](product-roadmap.md). Unmapped accounts
on real TBs directly affect statement accuracy — not a separate later concern.

**Status:** implemented in code — pending review and deploy. See migration
`g7h8i9j0k1l2_rename_accruals_canonical_line.py` for the `accruals` rename.

---

## Future consideration (not this round)

Broader financial-statement line-item review flagged two additional **SME-relevant**
gaps for a later expansion — not part of the six-line build above:

- **`due_from_to_related_parties`** — director loan accounts; very common on real
  Irish/UK SME trial balances.
- **`right_of_use_assets` / `lease_liabilities`** — increasingly required under
  FRS 102 lease accounting changes.

**Deliberately out of scope** for the current target market (reviewed, not
oversights): broader enterprise / public-company concepts such as non-controlling
interest, EPS, discontinued operations, equity-method investments, treasury
stock, and similar items.

---

## New canonical lines to add (6)

Matched to real FRS 102 / Irish–UK statutory terminology:

| Canonical line | Statement role | Absorbs (examples from live testing) |
|----------------|----------------|--------------------------------------|
| `investments` | Fixed asset | Long-term investments — distinct from `property_plant_equipment` and `intangible_assets` |
| `prepayments_and_accrued_income` | Current asset | Prepayments + Accrued Income (standard statutory presentation combines these) |
| `provisions` | Liability | Warranty provisions, etc. — distinct from `trade_payables` / `loans` |
| `taxation_and_social_security` | Liability | VAT Control + PAYE/NI Control + Corporation Tax Payable (standard small-company FRS 102 Section 1A presentation) |
| `share_premium` | Equity | Share premium — distinct from `share_capital` |
| `revaluation_reserve` | Equity | Revaluation reserve — distinct equity reserve |

---

## Confirmed NOT needing new lines

- **Provision for Bad Debts** — nets against `trade_receivables` as a contra-asset
  (same proven pattern as accumulated depreciation netting against
  `property_plant_equipment`).
- **Long-term Investments** — covered by the new `investments` line above.

---

## Deliberate choice: amortisation stays on `depreciation`

**Amortisation** was tested and currently maps to `depreciation` via the
existing **7000–7999** code-range rule in Tier 3 (`mapper.py`). This is a
**reasonable simplification** for a management-accounts tool — not a genuine gap
like the six additions above.

Both are non-cash charges that behave identically on the SOPL. **Decision:**
leave combined with `depreciation` for now. Revisit only if real customer
feedback specifically asks for separation. This is a **deliberate choice, not an
oversight**.

---

## Flagged design decision — requires migration (separate review)

Consider renaming / redefining **`accruals`** → **`accruals_and_deferred_income`**
to properly absorb **Deferred Revenue** per standard statutory presentation.

**Implemented:** code + Alembic data migration `g7h8i9j0k1l2`. Production had one
row (`JIE JIE LTD` / account `2100` / client `JIE HAN`) at time of build.

This changes an **existing** canonical line, not just adds a new one. Requires a
**data migration** for any `account_mappings` rows already using `accruals` — not
only updating the allowed-values list.

Needs its own careful review before implementing, **separate from** the six
straightforward additions above.

---

## Implementation touchpoints (six additions)

When implementing, keep these in sync:

| Area | Location |
|------|----------|
| Appendix A / product spec | `docs/product-spec.md` canonical lines list |
| Frontend dropdown | `frontend/lib/constants.ts` — `CANONICAL_LINES` |
| LLM Tier 4 allowlist + prompt | `backend/app/services/llm.py` — `MAPPING_TIE_BREAKER_CANONICAL_LINES` and `MAPPING_TIE_BREAKER_SYSTEM` |
| Shared constant (if used) | `shared/canonical_accounts.py` |
| API validation | `backend/app/routers/trial_balances.py` (confirm mapping against allowlist) |
| Statement Builder SOFP order | `backend/app/services/statements.py` — assign each new line a specific position in the existing structure |
| Tier 3 code-range table (optional) | `backend/app/services/mapper.py` — only if any new line should get code-range auto-mapping; **not required initially** — can launch as always-manual / Tier-4-only lines |

Also update: validator rules, export templates, and tests that assert canonical
line sets.

---

## Related gaps

- Mapping UI cannot yet distinguish "waiting on Tier 4" vs "no canonical match
  exists" — see [`tracked-gaps.md`](tracked-gaps.md).
- Materiality / variance work should ship first — see
  [`product-roadmap.md`](product-roadmap.md) Close tier.
