# Canonical lines expansion

Design for expanding Appendix A's mappable canonical set, confirmed via live
testing with a complex 74-account trial balance (see
[`tracked-gaps.md`](tracked-gaps.md) — Appendix A canonical set section).

**Sequencing:** fast-follow after Variance Analysis and materiality
auto-suggestion on the [product roadmap](product-roadmap.md). Unmapped accounts
on real TBs directly affect statement accuracy — not a separate later concern.

**Status:** implemented. Final design is Option A (granular, regime-neutral
lines) after a mid-build course correction — see below.

---

## Final design — Option A (confirmed)

**Decision:** keep the platform genuinely general-purpose. Do **not** bake in a
single jurisdiction's statutory presentation by combining economically distinct
accounts into FRS 102 Section 1A-style composite lines.

Three combined lines that appeared in the first expansion draft were **split
into granular, regime-neutral lines**:

| Combined (withdrawn) | Split into |
|----------------------|------------|
| `taxation_and_social_security` | `taxes_payable`, `social_security_payable` |
| `prepayments_and_accrued_income` | `prepayments`, `accrued_income` |
| `accruals_and_deferred_income` | `accruals`, `deferred_income` |

**Reasoning:** a general-purpose mapping layer should not assume UK/Irish small-
company statutory bundling. VAT, PAYE/NI, corporation tax, prepayments, accrued
income, accruals, and deferred revenue are distinct economic concepts; users in
other regimes (and many UK/IE management packs) keep them separate. Granular
lines can always be presented together later in a jurisdiction-specific export —
the reverse is harder once data is fused.

**Course correction note:** this was **not** the original expansion plan. The
first implementation shipped combined names (and renamed `accruals` →
`accruals_and_deferred_income` via migration `g7h8i9j0k1l2`). Option A reverts
that bundling mid-build. Migration `h8i9j0k1l2m3` restores the production
`JIE JIE LTD` / `2100` Accruals row to `accruals`.

Net since session start: **9 new mappable lines** (original six concepts, with
three of those concepts expanded into two lines each, plus restored `accruals`
as its own line again and new `deferred_income`).

---

## New canonical lines (final set)

| Canonical line | Statement role | Absorbs (examples from live testing) |
|----------------|----------------|--------------------------------------|
| `amortisation` | P&L expense | Amortisation of intangibles — distinct from `depreciation` (Option A) |
| `investments` | Fixed asset | Long-term investments — distinct from `property_plant_equipment` and `intangible_assets` |
| `prepayments` | Current asset | Prepayments |
| `accrued_income` | Current asset | Accrued income |
| `provisions` | Liability | Warranty provisions, etc. — distinct from `trade_payables` / `loans` |
| `accruals` | Liability | Accrued expenses (restored; was briefly renamed then split) |
| `deferred_income` | Liability | Deferred / unearned revenue |
| `taxes_payable` | Liability | VAT Control, corporation tax payable, and similar tax liabilities |
| `social_security_payable` | Liability | PAYE/NI and similar employment-tax control accounts |
| `share_premium` | Equity | Share premium — distinct from `share_capital` |
| `revaluation_reserve` | Equity | Revaluation reserve — distinct equity reserve |

(`accruals` existed before this expansion; it is listed because the mid-build
rename+split restored it as a first-class line alongside new `deferred_income`.)

### SOFP display order (new lines)

**Assets** (after receivables, before cash): `prepayments`, then `accrued_income`.

**Liabilities** (after provisions, before loans): `accruals`, `deferred_income`,
`taxes_payable`, `social_security_payable`.

---

## Confirmed NOT needing new lines

- **Provision for Bad Debts** — nets against `trade_receivables` as a contra-asset
  (same proven pattern as accumulated depreciation netting against
  `property_plant_equipment`).
- **Long-term Investments** — covered by the new `investments` line above.

---

## Deliberate choice reversed: amortisation is its own line

**Earlier draft** kept amortisation on `depreciation` via the shared **7000–7999**
code-range rule. That was revisited under the same Option A standard as the
balance-sheet splits: economically distinct concepts stay separate on the face
of the SOPL.

**Final design:** `amortisation` is a mappable P&L canonical line, shown on the
SOPL immediately after `depreciation` and included in `compute_net_profit` /
operating profit. Tier 3 code-range **7000–7999 defaults to `depreciation`**,
but `_tier3_code_range` specialises names matching `\bamort` (amortisation /
amortization) to `amortisation` so those rows are not locked to depreciation
before Tier 4 can run. Accounts without an amort- cue in the name still map to
`depreciation` at 0.65.

Migration `i9j0k1l2m3n4` remaps `account_mappings` where
`canonical_line = 'depreciation'` and `source_name ILIKE '%amort%'` (P&L
Amortisation - Software / Goodwill rows). Accumulated amortisation contra-asset
rows on `intangible_assets` are unchanged.

---

## Future consideration (not this round)

Broader financial-statement line-item review flagged two additional **SME-relevant**
gaps for a later expansion:

- **`due_from_to_related_parties`** — director loan accounts; very common on real
  Irish/UK SME trial balances.
- **`right_of_use_assets` / `lease_liabilities`** — increasingly required under
  FRS 102 lease accounting changes.

**Deliberately out of scope** for the current target market (reviewed, not
oversights): broader enterprise / public-company concepts such as non-controlling
interest, EPS, discontinued operations, equity-method investments, treasury
stock, and similar items.

---

## Implementation touchpoints

When changing the mappable set, keep these in sync:

| Area | Location |
|------|----------|
| Appendix A / product spec | `docs/product-spec.md` canonical lines list |
| Frontend dropdown | `frontend/lib/constants.ts` — `CANONICAL_LINES` |
| LLM Tier 4 allowlist + prompt | `backend/app/services/llm.py` — `MAPPING_TIE_BREAKER_CANONICAL_LINES` and `MAPPING_TIE_BREAKER_SYSTEM` |
| Shared constant (if used) | `shared/canonical_accounts.py` |
| API validation | `backend/app/routers/trial_balances.py` (confirm mapping against allowlist) |
| Statement Builder SOFP order | `backend/app/services/statements.py` — assign each line a specific position |
| Validator sets | `backend/app/services/validator.py` — `ASSET_LINES` / `LIABILITY_LINES` / `EQUITY_LINES_SOFP` |
| Tier 3 code-range table (optional) | `backend/app/services/mapper.py` — only if a line should get code-range auto-mapping; **not required** for these lines (Tier-4 / manual) |

Also update: export templates and tests that assert canonical line sets.

### Migrations

| Revision | Effect |
|----------|--------|
| `g7h8i9j0k1l2` | Historical: `accruals` → `accruals_and_deferred_income` (superseded by Option A) |
| `h8i9j0k1l2m3` | Option A: `accruals_and_deferred_income` → `accruals` (restores JIE JIE LTD `2100`) |
| `i9j0k1l2m3n4` | Option A: amortisation-named P&L rows `depreciation` → `amortisation` |

---

## Related gaps

- Mapping UI cannot yet distinguish "waiting on Tier 4" vs "no canonical match
  exists" — see [`tracked-gaps.md`](tracked-gaps.md).
- Materiality / variance work should ship first — see
  [`product-roadmap.md`](product-roadmap.md) Close tier.
- Equity-total formula drift risk across call sites — see
  [`tracked-gaps.md`](tracked-gaps.md).
