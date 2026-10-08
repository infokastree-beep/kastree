# Tracked gaps

Known implementation gaps that are **accepted for now** but should not be forgotten.
Review this list before claiming a feature area is complete.

For product-level sequencing (three-product roadmap, what to build next vs defer),
see [`product-roadmap.md`](product-roadmap.md).

## Next-session priorities

**Order matters.** Technical confidence first (validate), then go-to-market
(scale). Do not invert this — same discipline as the rest of the build.

### Technical confidence (do these first)

1. **Further adversarial stress testing — GL and TB, Excel and PDF.** Continue
   the pattern that found the Tier 3 mapping bug. Push more complex cases than
   tonight’s tests across all four intake surfaces (TB Excel/CSV, TB PDF, GL
   Excel/CSV, GL PDF). Goal: find the next silent correctness failure before a
   client does.

   **Highest-priority sub-case (do this before broader messy-data sweeps):
   code-normalization safety.** Live probes showed the GL→TB engine can produce
   a TB that **passes the balance check but is silently mis-bucketed** — the
   failure mode current safeguards cannot catch, because the arithmetic is
   correct even when the classification is wrong (same risk shape as the Tier 3
   mapping bug). Confirmed shapes:

   - **Padding / whitespace variants:** `"1000"` vs `"01000"` (and similar)
     stay as **separate accounts**; whitespace around codes is stripped today,
     but zero-padding is not normalized.
   - **Missing-code splitting:** blank codes become unique `UNCODED-{row}` per
     line, so the same account name with no code does **not** merge — one real
     account can shatter into many balanced-looking rows.

   **Priority work before wider messy-data testing:** (a) normalize account
   codes consistently (strip whitespace / padding rules decided and tested);
   (b) reconsider whether same-name / missing-code rows should merge (or fail
   closed for review) instead of silent `UNCODED-N` splits. Only then expand
   into inconsistent naming, mixed dates, duplicates, rounding, encodings.
2. **One real Live-mode Stripe payment.** Test-mode Checkout + webhook is
   proven ([Paywall](#paywall--done-2026-09-07)); the final unverified link is
   webhook-driven paid status on a genuine Live charge. Complete one end-to-end
   Live payment and confirm org tier/status updates from the Live webhook.

### Deferred enhancements (low priority)

- **Auto-run risk analysis on upload/mapping (deferred — future consideration).**
  Today risk flags are generated on demand via `POST /trial-balances/{id}/risk`
  (the Risk tab triggers it). Auto-running would remove a manual click. Decision:
  **defer**, not because it is high-risk in isolation (`evaluate_risks` is
  deterministic, no LLM), but because doing it *well* is a core async-pipeline
  behaviour change rather than a one-line toggle:
  - Timing matters — the most useful risk output needs **variance + statements**
    to exist first (e.g. unusual-variance-history rules), so the natural hook is
    *after* statement generation, not at upload/mapping-confirm. Running it at
    upload would produce partial (account-level only) flags that then need
    re-running, risking stale/duplicate flags.
  - It touches the `tb_pipeline` / statements-generation flow and needs its own
    idempotency handling (delete-and-reinsert already exists in the endpoint) plus
    pipeline tests. Best delivered as its own small PR, not bundled into unrelated
    work.
  Recommended shape when picked up: trigger `evaluate_risks` + persist as a final
  step of the statements-generation path (where variance is already available),
  guarded so re-generation replaces prior flags. Until then, the manual endpoint
  remains the supported path.

### Go-to-market (after technical confidence)

3. **Socials setup and content.** Profiles, basics, and a small set of posts
   that match the live product pitch — not a content machine before outreach.
4. **Direct outreach to prospective clients.** Highest-priority, most-deferred
   action across this entire session. Warm conversations beat polished channels;
   start this as soon as (1)–(2) are closed, in parallel with light socials.
5. **Paid advertising (LinkedIn, accountants)** — only once outreach is moving
   and there is initial signal. See
   [LinkedIn ads](#linkedin-ads--accountants--fractional-cfos-after-hero-is-live).
   Ads validate the public funnel; they do not replace (4).

## Archival write paths

Clients, companies, and trial balances soft-delete write to `archived_records`. See
`backend/app/routers/clients.py` module docstring for detail.

| Entity | Gap |
|--------|-----|
| `trial_balances` | **Done** — `DELETE /trial-balances/{id}` soft-deletes (`is_deleted` / `deleted_at`) and writes `archived_records` (`entity_type=trial_balance`). |
| `financial_statements` | `archived_records.entity_type` includes statements, but no delete/archive write path (statements are replaced in place on regenerate; no soft-delete column). |

### Soft-delete does not cascade — stranded children (accepted)

Soft-deleting a **client** or **company** archives that row only. Child records
(companies under a deleted client; trial balances under a deleted company) stay
`is_deleted=false` in the database but are **unreachable via any UI/API path**
(list/get joins filter the deleted parent). This is **consistent, deliberate
behaviour** — same rule at both levels — not a bug. Those stranded rows exist
indefinitely unless a future admin/cleanup tool surfaces or purges them.

## No company-details edit UI after create

**Resolved (UI shipped).** ClientDetail company cards now have **Edit company**
(next to Upload / Delete). Prefills name, currency, company number, industry,
and `company_type`; saves via `updateCompanyEntity` → `PUT /companies/{id}`.

**Currency behaviour (warn, don’t block):** upload stamps `trial_balances.currency`
from the company at upload time, but statement/export display uses live
`Company.functional_currency` via `_get_tb_functional_currency`. Changing
currency therefore **relabels** existing statements/exports without converting
amounts; future uploads store the new code. The edit form warns when the
company already has TBs.

**company_type:** trading↔holding clears `materiality_suggestion_dismissed_at`
(banner resurfaces) but does **not** overwrite applied materiality thresholds;
future suggestions use PBT vs equity per type.

## Clerk webhook payload persistence

Clerk webhook payloads are **not persisted** anywhere (unlike Stripe's
`subscription_events` table). After processing, the only audit trail is
structured application logs (`clerk_webhook_*` events in `app/routers/auth.py`).

**Not urgent.** If audit or replay becomes necessary, add a `clerk_webhook_events`
table mirroring `subscription_events`: Svix message id, event type, full payload
(JSONB), `processed_at`, and optional handler outcome. Until then, historical
delivery `type` fields cannot be reconstructed from the database alone.

## Webhook concurrency (test coverage)

`provision_first_signup` handles concurrent duplicate `organization.created`
deliveries via `IntegrityError` recovery, but the HTTP idempotency test only
covers the serialised “org already exists” path — not true parallel delivery.
See `backend/tests/test_api.py` (`test_duplicate_provision_first_signup_*`).

## Stripe webhook org resolution order (resolved)

`resolve_org_id` previously looked up `stripe_customer_id` before
`stripe_subscription_id`. The SQL helpers use `LIMIT 1`, so duplicate Stripe
ids in the database (common in long-lived dev DBs after test runs) caused
subscription events to update the **wrong** organisation — tier/status looked
unchanged on the org the test (or user) was watching. **Fix:** when both ids are
in the payload, resolve each column independently and reconcile (prefer
subscription id for `customer.subscription.*` / `invoice.*` on mismatch);
fall back to subscription-only or customer-only lookup. Webhook API tests now use
per-run unique Stripe ids so they stay isolated on polluted dev databases.

## SET LOCAL cleared by `commit()` — migration test anti-pattern (resolved)

`set_rls_org_id` / `aset_rls_org_id` use `set_config(..., is_local=true)` (Postgres
`SET LOCAL`), so `app.current_org_id` is cleared when the transaction ends.
Two data-migration tests (`test_amortisation_migration_*`,
`test_option_a_migration_*`) called `session.commit()` then continued
`account_mappings` DML/SELECT without re-setting RLS. Policies evaluate
`current_setting('app.current_org_id')::UUID`; after commit that GUC is `''`,
which raised `invalid input syntax for type uuid: ""` (not a silent empty
result set).

**Confirmed:** test-only anti-pattern. Full production audit of every
`set_rls_org_id` / `aset_rls_org_id` call site found **zero** application paths
that commit mid-session and continue RLS-protected work without re-setting
(background jobs already re-set after each commit; request handlers that
mid-commit only schedule BackgroundTasks and return). Even if the pattern
appeared in production, the failure mode is **loud and safe** (exception /
500 from the UUID cast), not fail-open cross-tenant leakage.

**Fix:** re-call `set_rls_org_id(session, org_id)` after each `commit()` before
further `account_mappings` access in those two tests. Also `session.expire_all()`
after raw SQL UPDATEs so ORM re-reads are not stale (`SyncSessionLocal` uses
`expire_on_commit=False`).

## Local `findraft` login bypasses RLS — test with `findraft_app`

`findraft` itself is the correctly-provisioned, non-superuser production role, confirmed via direct `pg_roles` query on 2 October 2026.

Phase 5 of the Product 1 stress test (30 September 2026) confirmed row-level
security with `app.current_org_id` set to organisation B: a direct `SELECT` of
organisation A's trial balance returned 0 rows. Cross-org API calls still
returned 404.

The default local development login `findraft` (the user in local `DATABASE_URL`
/ `DATABASE_URL_SYNC`) is a PostgreSQL superuser on a machine where that role
was created with superuser rights. Superusers bypass row-level security even
when `FORCE ROW LEVEL SECURITY` is on, so the same query run as that local
login still sees every tenant. Production connects as non-superuser `findraft`.

**Reminder:** any future local RLS test on a superuser `findraft` login must
connect explicitly as `findraft_app`. A test run as that superuser will look
like a tenant leak even when the policies are correct.

## Tier 4 OpenAI in sync BackgroundTasks (event-loop blocking)

`run_parse_and_map_job` (`backend/app/services/tb_pipeline.py`) invokes Tier 4
mapping via synchronous `OpenAI()` calls inside a sync `BackgroundTasks`
function. Fine when the call fails fast (e.g. missing `OPENAI_API_KEY`, as in
the walkthrough), but a genuine risk of blocking the entire async event loop if
a real key is set and a call is slow to respond or hangs.

**Before Tier 4 is used with a real key in anything beyond a one-off local
test:** make the LLM path properly async (e.g. `asyncio.to_thread` / executor
at minimum) or move parse/map to a real task queue per the Celery/Redis Month
3+ plan. See also `backend/app/services/mapper.py` (`apply_llm_tie_breaker`).

## Tier 4 LLM mapping — never tested with a real `OPENAI_API_KEY`

Tier 4 LLM mapping has **never been tested with a real `OPENAI_API_KEY` in this
environment** — every SOFP-side account on every fresh company falls through to
manual mapping, correctly but expensively. Real Tier 4 testing (with a genuine
API key) would confirm whether it actually resolves ambiguous **1000–3999**
range accounts by name reliably, which is the actual, designed fix for “why do
I have to map SOFP accounts manually every time.”

This is the **single biggest lever** for reducing manual mapping burden on new
companies — worth prioritizing getting a real key configured and tested over
further mapper logic changes. Pair with the event-loop note above before
enabling a real key in production BackgroundTasks.

## Appendix A canonical set — real-world coverage (scope question)

The 19-line mappable canonical set in Appendix A (dropdown, mapper Tier 4,
`MAPPING_TIE_BREAKER_CANONICAL_LINES`) may be missing common real-world account
categories. Manual testing flagged likely gaps — **prepayments**, **accrued
income**, **deferred/unearned revenue**, and **provisions** — none of which
cleanly fit any existing canonical line today.

**Confirmed via live testing (complex 74-account TB, no `OPENAI_API_KEY`):** 31
accounts fell to unmapped — correctly, since Tier 4 fails safely without a key.
Among those 31, seven are the **known canonical-gap types** above plus related
control / equity lines that have no clean Appendix A home even with a working
LLM:

- Prepayments
- Accrued Income
- Deferred Revenue
- Provisions — Warranty
- VAT Control Account
- **VAT Recoverable / VAT receivable** (asset owed *to* the entity — distinct from
  VAT Payable / `taxes_payable`) — **resolved** via `other_receivables` (misc
  current asset leaf; name cue + dropdown + LLM allowlist). Do **not** force
  `taxes_payable` or `trade_receivables`.
- PAYE/NI Control Account
- Revaluation Reserve

The mapping UI currently treats these the same as ordinary accounts (e.g. Cash,
Trade Debtors, Share Capital) that would likely resolve once Tier 4 actually
runs. There is no way to tell **"this just needs Tier 4 to execute"** apart from
**"this will genuinely never have a good match, no matter what."**

**Consider for a future session:** distinguish the two cases in the mapping UI
— e.g. a small hint or tag on rows where even Tier 4 (if it ran) has no
confident canonical match available, versus rows simply waiting on Tier 4.
**Not urgent** — capture the confirmed real-world finding so it is not lost.

**Not a bug — a scope question for a future session.** Review against real
client trial balances (not synthetic test data) before deciding whether to expand
the canonical set. If expanded, scope the downstream changes: Statement Builder
line placement, validator rules, frontend dropdown/constants, and LLM tie-breaker
prompts must stay aligned.

**Proposed expansion (6 new lines + migration note for `accruals`):**
[`canonical-lines-expansion.md`](canonical-lines-expansion.md). Sequenced on the
[product roadmap](product-roadmap.md) as fast-follow after Variance / materiality.

## `capital_contribution` canonical line

**Resolved.** Capital Contribution Reserve is common enough in Irish/UK FRS 102
filings (especially group subsidiaries and parent funding without share issue)
to warrant its own equity leaf. Mapping it to `share_premium` is **not**
sufficient: capital contribution is non-statutory equity and is not legally
equivalent to share premium (Companies Act / TECH distributable-profits
guidance; Irish filed accounts present it as a separate face line).

Added `capital_contribution` to `EQUITY_COMPONENT_LINES` (SOFP face after
`share_premium`, before `retained_earnings`), frontend dropdown, Tier 4
allow-list / mapping-tie-breaker-v5 prompt, Appendix A, and shared constants.
SOCIE/validator totals pick it up via `compute_total_equity`. SOPL unchanged.

## Equity total — duplicated inline formulas (structural drift risk)

**Resolved.** Total equity is no longer hand-summed in four places. A single
shared `compute_total_equity(amounts_by_line)` in `backend/app/services/statements.py`
sums every entry of `EQUITY_COMPONENT_LINES` (`share_capital`, `share_premium`,
`capital_contribution`, `retained_earnings`, `revaluation_reserve`). All four
former drift sites call it:

- `build_sofp` → SOFP `total_equity`
- `_compute_socie_rollforward` / `build_socie` → SOCIE `total_equity_closing`
- validator `_total_equity_sofp` → Check 4 `net_assets`
- validator `_total_equity_balance_sheet` → Check 2 `balance_sheet_balance`

Adding a future equity face line means extending `EQUITY_COMPONENT_LINES` (and
display metadata) once — not patching four formulas. Regression coverage:
`test_four_equity_total_sites_all_call_compute_total_equity` and
`test_new_equity_canonical_line_cannot_diverge_across_four_call_sites` (would
have caught the share_premium / revaluation_reserve misses on all four sites at
once). Live proof: charlie munger / berkshire periods with nonzero share_premium
(25,000) and revaluation_reserve (18,000) recomputed bit-exact to stored
SOFP/SOCIE totals (327,600.00) across four period ends.

## CreateClientForm step-1-only recovery (misleading empty state)

`CreateClientForm` is a two-step flow: step 1 creates the client group (`POST
/clients`); step 2 creates the first company (`POST /clients/{id}/companies`). If
a user completes step 1 but abandons or errors out before step 2, the client
group **persists** and remains visible — it is not a dead end. `ClientsList`
shows **0** in the Companies column; `ClientDetail` shows **0 companies** in
the header and an empty-state message.

The recovery action on `ClientDetail` is **semantically wrong**: the empty state
links to **+ New client** (`/clients/new`), which starts a **new** client group
rather than adding a company to the existing one. A user recovering from an
abandoned step 2 could create duplicate/orphaned client groups (each stuck at 0
companies) instead of finishing the one they started.

**Follow-up, not urgent.** Add a proper **Add company** action on `ClientDetail`
that calls `POST /clients/{id}/companies` directly from that page — not routed
through `CreateClientForm`'s two-step flow. Step 2 of create remains the happy
path for new client + first company; detail-page add company is the recovery
path for client groups with zero companies.

**Resolved:** `ClientDetail` now has a **+ Add company** action that posts to
`POST /clients/{id}/companies` with the same fields as `CreateClientForm` step 2.

## Materiality thresholds — static defaults vs benchmark-based suggestion

Materiality thresholds are currently **static, manually entered values** (default
10% / 1000 absolute) with **no connection to the company's actual financial
profile**.

**Important scope note:** auto-suggestion can only run **after** a company's
first trial balance is uploaded and statements are generated — not at
company-creation time, since no real financial figures exist yet. The company
creation form will always need to show generic static defaults (as it does now).
The smart-suggestion step is a **post-first-upload** prompt — e.g. "here's a
better materiality threshold based on your real numbers — apply it?" — not
something requested upfront during setup.

### Target design (deferred)

Materiality auto-suggestion should be based on real, established audit-materiality
benchmarking (ISA 320-derived), used here purely as a **sensible SaaS default
suggestion** — **not** implying the product performs audit-grade materiality
judgments, which remain the accountant's own professional responsibility.

**Benchmark selection by company type:**

| Company type | Benchmark |
|--------------|-----------|
| Profit-oriented / trading companies | 5–10% of Profit Before Tax (continuing operations) |
| Startups, charities, low-margin / high-revenue firms | 0.5–3% of Total Revenue / Turnover |
| Capital-intensive companies or investment funds | 1–3% of Total Assets |
| Holding companies / balance-sheet-focused entities | 3–10% of Net Assets / Equity |

**Risk-based adjustment within each range:**

- **Lower end** (more conservative) if: weak internal controls, complex
  business, first-time engagement, publicly traded / external-finance-dependent.
- **Higher end** if: stable operations, owner-managed with no external finance
  dependency.

**Additional levels worth eventually supporting** (not just a single threshold):

- **Performance materiality** — a lower working threshold, typically 50–75% of
  overall materiality, for catching smaller aggregated errors during review.
- **Trivial threshold** — ignore clearly inconsequential items, typically 3–5%
  of overall materiality.

**Implementation approach:** default to mid-range percentages; let the user
(accountant) adjust based on their own judgment of risk / company type. Present
as a smart, editable starting suggestion — never as an authoritative audit
determination. Requires the company-type classification already noted (holding
vs trading) as a prerequisite.

**Manual benchmark override on the suggestion banner (considered 2026-09-05 —
declined):** do **not** add a per-banner control to pick revenue / assets / PBT /
equity as the suggestion base. The banner stays an indicative default keyed off
`company_type` (trading → PBT, holding → equity); override path remains dismiss
+ edit thresholds (and company type) on the company settings. If more precision
is ever needed, expand `company_type` (e.g. high-revenue / NFP → revenue-based
mid-range) rather than a free-form benchmark picker on the banner.

**Still deferred** — no data exists to auto-calculate against until a company's
first real upload — but this is the actual target design once built, not a vague
"something better" placeholder.

**Source:** standard audit materiality practice (ISA 320 framework; commonly
cited ranges from professional audit guidance).

**ISA 320 user-facing copy — settled (2026-09-06):** keep the live disclaimer
exactly as written — no speculative removal. Confirmed on production
(`/trial-balances/{tb_id}/materiality-suggestion` → `disclaimer`):

> Indicative SaaS default from ISA 320-style benchmarks — not an audit determination.

Source of truth: `DISCLAIMER` in `backend/app/services/materiality.py`. Decision
rationale: naming ISA 320 with “-style” + the non-audit disclaimer is honest,
standard accounting-software framing (akin to citing GAAP/IFRS/FRS by name);
it is **not** treated as an open product question or a reason to strip the
reference pending legal review.

**One remaining legal item (not urgent; not blocking copy):** if/when formal
legal review is sought, include these specific questions:

1. Is nominative use of “ISA 320” / “ISA 320-style” in a SaaS
   materiality-suggestion UI acceptable with the current disclaimer
   (“not an audit determination”)?
2. Any trademark considerations around ISA® / IAASB branding?
3. Does the current disclaimer + product ToS + internal-review-only
   positioning sufficiently protect against being “held out as audit tooling”?

Current copy is reasonable and **unchanged pending this** — not evidence of a
problem. Do **not** rewrite or remove the settled wording unless counsel
advises a change.

**Monthly cadence (confirmed 2026-09-03):** variance auto-detect and
month-over-month arithmetic already work with monthly `period_end` dates
(June then July upload through the real API — see
`test_monthly_cadence_upload_auto_detects_prior_variance`). The static
threshold (**>10% OR >1,000**) was **not** designed with monthly movements in
mind: a 60% month-on-month revenue swing is material under the same rule as a
60% year-on-year swing. When the benchmark-based auto-suggestion above is
built, it should consider **reporting frequency** (monthly vs quarterly vs
annual) as well as company type — not only the ISA 320 company-type table.

## Unusual variance history buckets vs monthly cadence

Risk Rule 2 (`unusual_variance`) tiers on **observation count**, not calendar
span: skip if history length &lt; 3; **3–11** flag when `abs(variance_pct) > 50`;
**12+** flag when `|current − mean| > 3 × sample stdev` over the last 12
percentages. Copy always says “N months of historical data.”

**Wired 2026-09-06:** `POST /trial-balances/{id}/risk` now loads prior
`variance_analyses` rows for the **same company** (`period_end < current`,
`status=complete`, non-deleted TBs) and passes the resulting
`{line_item_code: [variance_pct, …]}` map into `evaluate_risks()`. Cross-company
leakage is blocked by the `company_id` filter (same RLS discipline as the rest
of the stack). `unusual_variance_history_months` reports the prior-period count.

**Berkshire live calibration (13 variance runs, company `berkshire`):**

| Bucket | As-of | Result |
| --- | --- | --- |
| 12+ (3σ) | 2026-09-20 latest | **0 flags**. Dense lines sit at z ≈ 1.85–2.42 vs fat-tailed history (spikes to ~1470% / ~1714%). No false positives on this real series — **3σ kept**. |
| 3–11 (50% bar) | 2026-08-28 ordinary MoM (~15–20%) | **0 flags** — sensible. |
| 3–11 (50% bar) | 2026-08-30 / 2026-09-04 real spikes (500%+) | Flags fire as expected. |

Quiet synthetic MoM series can still trip 3σ at ~15% (unit test retained as a
known property). Berkshire’s **actual** fat-tailed MoM history does not, so
thresholds were **not** retuned. Revisit only if a quiet monthly client shows
false positives in production.

**Performance Overview still does not unlock Rule 2** — it stores absolute KPI
amounts, not per-line `variance_pct` history. The wiring source is
`variance_analyses` only.

## Financial statements — currency display (resolved)

Browser dashboard (`StatementsDashboard.tsx`) and export templates (`exporter.py`
Excel/PDF; CSV statement amounts) now show the company's `functional_currency`
and format statement amounts per Cursor Rules §10.7 (comma thousands for GBP/USD/EUR —
deliberate consistency override of European space grouping; currency symbol prefix;
minus sign for negatives).

## Trial balance upload — ClamAV virus scanning not implemented

Product Spec §4.1 / §12.2 requires ClamAV scanning on TB upload (reject if
infected). The upload handler (`POST /trial-balances/upload` in
`backend/app/routers/trial_balances.py`) currently validates only:

- file extension (`.xlsx` / `.csv` via `_file_extension`)
- size (50 MB max)

There is **no virus scan** — no `clamd` / `pyclamd` import anywhere in the
backend. `python-clamd==0.4.0` was listed in `requirements.txt` but that
package/version does not exist on PyPI (only `0.0.1.dev0` / `0.0.2.dev0` under
the `python-clamd` name; the `0.4.0` version lives under **`pyclamd`** instead).
It was removed from `requirements.txt` to unblock the Railway build.

**Follow-up:** wire ClamAV into the upload path before calling this area
production-ready for untrusted file intake. Likely packages on PyPI:
`pyclamd==0.4.0`, `clamd==1.0.2`, or `clamdpy==0.2.0` — all require a running
`clamd` daemon (not bundled). Scan should happen on the saved bytes **before**
`stored_path.write_bytes(content)` returns 202, rejecting infected files with
4xx. Add integration tests with EICAR when implemented.

## Object storage (S3/R2) — exports confirmed working in production

**Status (resolved 3 Sep 2026; confirmed working):** Cloudflare R2 bucket
`kastree-exports` is live with Object R/W credentials on Railway. Production
exports (xlsx / pdf / csv) succeed. Bucket lifecycle for `exports/` is also
live (next section).

**Historical context:** Before credentials were set, `boto3` raised
`NoCredentialsError` on `put_object` and export jobs landed in
`status="failed"`. The UI still surfaces a clear message if credentials are
ever absent: *"Object storage credentials are not configured…"*
(commit `030b8fc`+).

**Required env (now set in Railway):** `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `S3_BUCKET`, and for R2 `S3_ENDPOINT_URL`
(`https://<ACCOUNT_ID>.r2.cloudflarestorage.com`). See
`.env.production.example`.

## R2 lifecycle Admin token — `exports/` 30-day expiry (resolved)

**Resolved (3 Sep 2026):** Created Cloudflare R2 API token
**`kastree-exports-lifecycle-admin`** (Admin Read & Write, scoped to
`kastree-exports`) and applied Product Spec §12.2 / §12.6 via
`backend/scripts/configure_s3_lifecycle.py` using that Admin token — **not**
the Railway Object R/W token (`kastree-exports-backend`), which still returns
**AccessDenied** on lifecycle GET/PUT (expected; leave it as Object R/W for
app exports only).

**Live `GetBucketLifecycleConfiguration` on `kastree-exports` (Admin token):**

| Rule ID | Status | Filter | Expiration |
|---------|--------|--------|------------|
| `Default Multipart Abort Rule` | Enabled | (none — multipart abort only) | — (AbortIncompleteMultipartUpload 7d) |
| `findraft-exports-expire-30d` | Enabled | **Prefix `exports/`** | **Days = 30** |

Confirmed: no expiration rule on empty/whole-bucket prefix; no rule targets
`db-backups/`. Re-verify anytime with the Admin token:

`cd backend && python scripts/configure_s3_lifecycle.py --dry-run`
(or a one-shot boto3 `get_bucket_lifecycle_configuration`).

## R2 API token rotation — `kastree-exports-backend` (expires September 2027)

The Cloudflare R2 Account API token **`kastree-exports-backend`** (mapped to
`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` on Railway) expires **one year
from creation — September 2027**. Set a **calendar reminder to rotate it before
then** (e.g. August 2027).

**Rotation (simple):**

1. In Cloudflare → R2 → Manage R2 API Tokens, create a new Account API Token
   with the **same permissions** as `kastree-exports-backend`.
2. Update `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` on Railway with the
   new token values.
3. Redeploy (or let Railway pick up the env change).

**If the token lapses:** exports fail with the clear *"Object storage credentials
are not configured…"* error surfaced to the UI (not a silent failure). Fix by
rotating the token and redeploying.

## Trial balance uploads — local disk, not S3

TB files are written to `settings.upload_dir` (env: `UPLOAD_DIR`, default
`/tmp/findraft-uploads`) via `file://` paths in `trial_balances.file_url`.
Export files use S3/R2 (`backend/app/services/exporter.py`) once credentials
are configured (see section above).

**Short-term production fix:** mount a persistent volume (e.g. Railway
`/data/uploads`) and set `UPLOAD_DIR=/data/uploads`. **Proper fix:** upload TB
files to object storage and stop relying on local disk (same bucket family as
exports, or a dedicated `uploads/` prefix). Until then, redeploys without a
volume wipe uploaded files and multi-instance deploys will not share uploads.

## Waitlist signups — no authenticated way to view signups (resolved)

`POST /waitlist` is public (rate-limited per IP, unique email constraint). Rows
live in `waitlist_signups` with **INSERT-only RLS** for the `findraft` app role.

**Resolved:** `GET /admin/overview` (platform-admin allowlist + owner role) lists
waitlist signups cross-tenant via `app.platform_admin=true` RLS policies. See
`backend/app/routers/admin.py` and migration `j0k1l2m3n4o5_platform_admin_select_policies.py`.

## Admin visibility into organisations, users, and customers (resolved)

**Resolved:** `/admin` frontend page + `GET /admin/overview` backend endpoint
list organisations, users (with org name), and waitlist signups platform-wide.

**Security note (resolved):** access requires **both** `require_roles("owner")`
and an explicit `PLATFORM_ADMIN_EMAILS` allowlist — not every org owner.
See `require_platform_admin()` in `backend/app/dependencies.py`.

## Incident: /admin cross-tenant data exposure (resolved 2026-09-02)

**Severity:** High — any org owner could read all waitlist signups, organisations,
and users platform-wide via `GET /admin/overview`.

**Affected data:** Waitlist PII (name, email, firm), all organisation names/tiers,
all user emails and roles. **No trial balances, clients, companies, or financial
data** were exposed via this endpoint.

**Who could access it:** Any user with `role=owner` in any provisioned organisation.

**Who actually had accounts during the window:** Only three test organisations
created during this build session — all controlled by the founder, not external
customers:

| Account | Email | Organisation |
|---------|-------|--------------|
| Mark | `markdooling25@gmail.com` | Mark's Organization |
| Jie | `hanjie987@gmail.com` | Jie's Organization |
| kastree | `infokastree@gmail.com` | kastree's Organization |

**Waitlist rows during window (4 total):** all founder/test entries — Mark's own
email, `prod-waitlist-*@example.com`, and `markdooling25+*@gmail.com` test aliases.
No third-party customer waitlist signups existed.

**Timeline (all UTC, 2026-09-02):**

| Time | Event |
|------|-------|
| 22:37:32 | Commit `74fdcfc` ships `/admin` + `GET /admin/overview` gated only by `require_roles("owner")` — no platform-admin allowlist. |
| 22:37:34 | Railway deployment `fe32cb0f` goes live with ungated admin. **Exposure starts.** |
| 23:33:53 | Fix committed (`f6cb675` — `require_platform_admin()` + `PLATFORM_ADMIN_EMAILS`). |
| 23:33:54 | Railway redeploy `ce142529` triggered by setting `PLATFORM_ADMIN_EMAILS` env var — **still running `74fdcfc` code** because fix was pushed only to Cursor `origin`, not GitHub. Env var alone had no effect. |
| ~23:44 | **Discovered** — `infokastree@gmail.com` (kastree org owner) saw full platform admin data; should have received 403. |
| 23:44:24 | Fix pushed to `github/main`; Railway deployment `458660e0` goes live with `require_platform_admin()`. **Exposure ends.** |

**Exposure window:** ~**67 minutes** (22:37:34 → 23:44:24 UTC).

**Root cause:** Two-part failure. (1) Initial `/admin` shipped without platform-admin
allowlist. (2) Fix was committed and pushed to Cursor `origin` but **not** to
`github` (Railway's deploy source); setting Railway env vars redeployed stale code.

**Verification after fix:** Live production HTTP tests confirmed `infokastree@gmail.com`
and `hanjie987@gmail.com` → **403**, `markdooling25@gmail.com` → **200**.

**Structural safeguard added:** `scripts/verify_remotes_in_sync.sh`,
`scripts/verify_railway_deploy_marker.sh`, and `scripts/verify_security_deploy.sh`
— mandatory after security-relevant changes. See `docs/runbooks/deployment.md`
§ "Release verification (security changes)".

## Admin nav link — stale Vercel CDN (cosmetic only, deferred)

**Not a security gap.** The backend fix is live: `GET /admin/overview` requires
`require_platform_admin()` and returns **403** for non-founder org owners
(`infokastree@gmail.com`, `hanjie987@gmail.com`). Verified in production.

**Cosmetic frontend gap:** the **Admin** nav link can still appear for non-founder
org owners because production Vercel CDN is serving a **stale frontend bundle**
that gates the link on `me.role === "owner"` instead of `me.is_platform_admin`.

The corrected code is on `github/main` (commit `3686d9a` and later): `/users/me`
exposes `is_platform_admin`, and `AdminNavLink` uses that flag. Local production
builds include the expected dashboard layout chunk
(`layout-225113b4a668b925.js` with `is_platform_admin`). `scripts/verify_vercel_deploy_marker.sh`
confirms the marker is **404 / absent** on `https://www.kastree.ie` as of
2026-09-03.

**Vercel deploy status (2026-09-03):** multiple redeploy attempts and cache clears
tonight did **not** get the new chunk onto the production CDN — worth investigating
fresh in a future session (possible Vercel-side caching, root-directory, or build
configuration issue). **Do not keep forcing redeploys in the same session.**

**Confirmed still stale (2026-09-06, morning):** live `https://www.kastree.ie` meta
`kastree-git-sha` = `b932f8e7e6c1be980a91516414e87d426ab3e92e` (**6 commits
behind** then-HEAD). That SHA predates materiality settings + Delete company.

**Root cause (confirmed 2026-09-06, evening — not flaky Vercel auto-deploy):**
Cloud Agent pushes went to Cursor `origin` only. Vercel + Railway watch
**GitHub** (`github` remote → `infokastree-beep/kastree`). `github/main` was
still at `b932f8e` — identical to the live meta SHA — so Vercel correctly never
rebuilt. Auto-deploy is reliable once GitHub moves; the failure mode is
**dual-remote drift**.

**Resolved 2026-09-06:** `git push github HEAD:main` advanced GitHub to
`5299f2e`; Vercel Production rebuilt in ~1 minute; live meta
`kastree-git-sha` = `5299f2eea1791a2dbf0f216cefb5f24696092334`. Live company
cards now show **Materiality thresholds** + **Delete company** (verified in
browser).

**Permanent safeguards (already partially in place; completed this fix):**

1. **Always push both remotes:** `./scripts/push_production_remotes.sh`
   (optionally `--verify-live` to poll the meta tag).
2. **`./scripts/verify_remotes_in_sync.sh`** — fails if `origin/main` ≠
   `github/main` (updated to call out Vercel as well as Railway).
3. **CI on every GitHub `main` push:**
   `.github/workflows/verify-production-frontend.yml` polls
   `www.kastree.ie` for `<meta name="kastree-git-sha">` matching `github.sha`
   and **fails the workflow** if production stays stale (~15 min). Optional
   secret `VERCEL_DEPLOY_HOOK_URL` can force a Production redeploy first.

That CI check never fired during the lag because GitHub never received the
commits — pushing to `github` is the missing link, not a new Vercel product
bug.

**Until agents habitually use `push_production_remotes.sh`:** any
origin-only push will recreate this exact “Vercel silently behind” symptom.

**Deploy hook — resolved (2026-09-07):** both paths that need
`VERCEL_DEPLOY_HOOK_URL` are covered:

| Path | Status |
|------|--------|
| GitHub Actions `secrets.VERCEL_DEPLOY_HOOK_URL` | Working — `verify-production-frontend.yml` POSTs the Production hook on `main` pushes (proven live). |
| Cloud Agent / local `scripts/trigger_vercel_deploy.sh` | Working — same Production/`main` hook URL saved as a Cursor **My Secrets** entry (`VERCEL_DEPLOY_HOOK_URL`, applies to all repositories). Available to **new** Cloud Agent sessions going forward. |

Prefer dual-remote push + SHA guard as the default path; the hook remains the
kick when Git is connected but a build still needs a nudge.

## Production users table — placeholder Clerk emails

Some production `users.email` rows still show `@users.clerk.pending` placeholders
instead of real addresses. **Root cause:** Clerk's `organization.created` webhook
payload does not include email fields — only `created_by` (Clerk user id). The
handler previously fell back to a placeholder when email was absent; it now
fetches the real address from the Clerk Users API and `user.updated` can refresh
stale rows.

**Low priority** for product behaviour (auth uses Clerk ids, not our email column),
but **do not rely on the admin user list for outreach** until placeholders are
backfilled. Run `backend/scripts/backfill_user_emails_from_clerk.py` against
production, or wait for `user.updated` webhooks after enabling them in Clerk.
**2026-09-02:** all three production users were backfilled from Clerk
(`hanjie987@gmail.com`, `markdooling25@gmail.com`, `infokastree@gmail.com`).

**Not Google OAuth-specific** — affects all sign-up paths when email is missing
from the org webhook payload.

## Clerk Users API lookup — implicit httpx timeout

`fetch_clerk_user_primary_email()` (`backend/app/services/clerk_users.py`) calls
the Clerk Backend API via the `clerk-backend-api` SDK with `timeout_ms` unset,
so it relies on **httpx's default timeout** (~5s) rather than an explicit value.

**Worth setting `timeout_ms` explicitly** on the SDK call for predictable,
faster-failing behaviour under a slow Clerk API response — e.g. a short connect
+ read budget so provisioning webhooks don't sit blocked on library defaults.

**Low priority** — not a correctness fix. Fail-soft behaviour already handles
lookup failures (placeholder email + `user.updated` / backfill path), and Clerk's
own webhook retry mechanism covers transient stalls. This is a
**latency/predictability** improvement only.

## `trial_balances.currency` — redundant with `companies.functional_currency`

Upload now **forces** `trial_balances.currency` from `company.functional_currency`
(server-side, ignoring the form field). Statements GET/POST and exports already
read currency from the **company** row (`_get_tb_functional_currency`), not from
the TB column. The TB field is still referenced in `tb_pipeline.py` for parser
metadata fallbacks (`tb.currency or "GBP"`).

**Not urgent.** The column duplicates its parent and can drift if company currency
is edited after upload (pre-upload enforcement prevents new mismatches). A future
cleanup migration could drop `trial_balances.currency` and route all reads through
`companies.functional_currency` (with a one-time backfill/consistency check). Until
then, keeping the column is low-cost denormalization with no user-facing benefit.

## Infrastructure — pull request tests, and Product 1 RLS casts an empty org id

The Product 1 policy gap below is unchanged.

**GitHub pull requests run the test suite.** `.github/workflows/pr-tests.yml` starts Postgres 15. The backend job connects as a superuser login named `findraft`, creates the non-superuser `findraft_app` role before migrating, applies migrations from an empty database (upgrade to `a1b2c3d4e5f6`, then `backend/scripts/bootstrap_stripe_rls_lookup.sql`, then upgrade to head), and fails if pytest fails. A parity job migrates as the `postgres` superuser, runs `backend/scripts/provision_findraft_app_role.sql`, and runs the HTTP tests with the API logged in as `findraft` (`NOSUPERUSER`, `NOBYPASSRLS`). Tests that cannot run as that login are listed in `backend/scripts/parity_excluded_tests.txt` and still run in the backend job. The client-erasure archive read and the week-10 draft-operation insert now set `app.current_org_id` and run in the parity job. `tests/test_findraft_privileges.py` fails the build if `findraft` holds `TRUNCATE`, `REFERENCES`, or `TRIGGER` on any public table, or `UPDATE`, `DELETE`, or `TRUNCATE` on an append-only or fully immutable table. The workflow also fails if the frontend `test:*` scripts, `ruff check app`, or `mypy --strict --follow-imports=silent` on `backend/mypy_clean_modules.txt` fails. Project-wide `mypy app` is not a pull-request gate. `.github/workflows/verify-remotes.yml` still only prints the commit SHA. Pushing to `main` also runs `verify-production-frontend.yml`, which checks that www.kastree.ie serves that SHA. That workflow is not a test run.

## mypy — 99 project-wide errors, not a pull-request gate

`mypy app` from `backend/` (mypy 1.13, config in `backend/mypy.ini`) reports **99 errors in 13 files** (144 files checked). These are existing debt. Pull requests gate `mypy --strict --follow-imports=silent` on the 117 modules in `backend/mypy_clean_modules.txt`, which currently report zero errors. Do not silence the 99 by editing the financial parsers, the exporter, or billing just to make `mypy app` pass. Burn them down file by file.

Counts below are from `mypy app` (not `--strict`). Categories: **arg-type** 70, **import-untyped** 14, **attr-defined** 9, **assignment** 5, **union-attr** 1.

| File | Errors | Categories |
| --- | --- | --- |
| `app/routers/billing.py` | 36 | arg-type. `stripe.checkout.Session.create` called with `**dict[str, object]`. |
| `app/services/pdf_tb_extract.py` | 19 | 16 arg-type (`float(object)`), 3 import-untyped (`fitz`, `pytesseract`, `openpyxl`). |
| `app/services/exporter.py` | 10 | 6 import-untyped (`openpyxl`, `openpyxl.styles`, `openpyxl.utils`, `openpyxl.worksheet.worksheet`, `weasyprint`, `boto3`), 3 attr-defined (`put_object`, `generate_presigned_url`, `head_object` on `object`), 1 union-attr (`date \| None` has no `strftime`). |
| `app/routers/trial_balances.py` | 8 | 6 arg-type, 2 assignment (`FinancialStatement` vs `ProcessingJob`). |
| `app/schemas/copilot.py` | 6 | 5 attr-defined (`EvidenceExpenseShare`), 1 assignment (`EvidenceVarianceItem`). |
| `app/services/export_job.py` | 6 | arg-type (`Export` vs `ExportStatusTarget`, `Organisation` vs `OrganisationTier`). |
| `app/services/parser.py` | 4 | 3 import-untyped (`openpyxl`, `pandas`, `fitz`), 1 attr-defined. |
| `app/services/gl_to_tb.py` | 4 | 2 import-untyped (`openpyxl`, `pandas`), 2 assignment. |
| `app/routers/export.py` | 2 | arg-type (`regenerate_export_if_missing`: `Export` vs `ExportStatusTarget`, `Organisation` vs `OrganisationTier`). |
| `app/services/tb_pipeline.py` | 1 | arg-type (`list[TBRow]` vs `Sequence[MappableAccount]`). |
| `app/routers/users.py` | 1 | arg-type (`role: str` vs the role `Literal`). |
| `app/routers/admin.py` | 1 | arg-type (`Sequence[Row[tuple[User, str]]]` vs `Sequence[tuple[User, str]]`). |
| `app/routers/risk.py` | 1 | arg-type (`list[object]` vs `Sequence[Mapping[str, Any] \| VarianceAnalysisResult]`). |

**Product 1 `companies` and `clients` policies cast the org setting without `NULLIF`.** `companies_org_isolation` uses `current_setting('app.current_org_id')::UUID` inside the client lookup, and `clients_org_isolation` uses `org_id = current_setting('app.current_org_id')::UUID`. There is no `NULLIF`. After `set_config('app.current_org_id', ..., true)` the setting is transaction-local, so `commit()` leaves it as `''`. The next statement on that connection then raises `invalid input syntax for type uuid: ""` instead of matching zero rows. Newer tables (source documents, trial-balance versions, fixed-asset versions, drafts, render jobs, confirmed mappings, and the audit-log chain) use `NULLIF(current_setting('app.current_org_id', true), '')::uuid`, which returns no rows when the setting is missing or empty. Do not change the Product 1 policies until that difference is chosen on purpose. A `NULLIF` form would hide the rows rather than raise, so a test that forgot to set the org id would update zero rows and continue.

## Infrastructure account ownership — personal email, not business entity

All infrastructure accounts started under a **personal email**, not a dedicated
business entity. **As of 3 Sep 2026 overnight cutover**, most ownership and
security work is done. What remains outstanding is the short list below — not a
general “everything is still on personal email” fog.

**Resolved and verified tonight (do not re-open without new evidence):**

- **GitHub** — repo at `infokastree-beep/kastree`; origin + github remotes in sync.
- **Vercel Git source** — reconnected to `infokastree-beep/kastree` after it
  silently stayed on `markdooling25-commits/kastree` post-transfer (see
  outstanding list item 2 / resolved note below). Verify source after any
  future GitHub-side change.
- **Clerk** — production instance live (`clerk.kastree.ie`); business email has
  Owner access (original owner cannot be removed yet — see section below; safe).
- **Railway (live stack)** — NEW project **overflowing-creation** under
  `infokastree@gmail.com` serves production behind www.kastree.ie; DB migrated;
  RLS re-proven; OLD delightful-purpose left as fallback only.
- **R2 lifecycle** — `exports/` 30-day expiry applied via Admin token (see
  resolved R2 lifecycle section above).
- **Security / cutover** — live API URL, health, soft-delete cleanup, privacy
  policy, Vercel Web Analytics wired and receiving data.
- **Railway billing (RESOLVED 2026-09-04)** — Subscribed to Railway Hobby plan
  ($5/month, includes $5 usage credit) on `infokastree@gmail.com` /
  **overflowing-creation**. Confirmed via live API: `isTrialing=false`,
  `state=ACTIVE`, subscription `sub_1UBkkRCJoPsRzQsdpzT2fyU7` active. Confirmed
  zero service disruption — no restart/redeploy around the billing transition,
  `GET /health` continuously 200 throughout. No more trial-credit exhaustion risk.

**Genuinely outstanding (complete final list from tonight):**

1. **Vercel project transfer** — still blocked by Vercel’s free **Hobby**-tier
   single-member limit, confirmed multiple times tonight against real docs/UI.
   Completing a transfer to the business account requires upgrading to **Pro**
   (about **$20/month**, at least temporarily) so a shared team can hold both
   members before the transfer finishes. **Not urgent** — production
   (www.kastree.ie) is fully live and working regardless of which account owns
   the Vercel project today (`markdooling25-commits` / kastree team).

2. **Vercel Git source after GitHub transfer (RESOLVED 2026-09-04)** — After the
   GitHub ownership transfer earlier tonight
   (`markdooling25-commits/kastree` → `infokastree-beep/kastree`), Vercel’s
   connected source repo **silently stayed on (or never updated from)
   `markdooling25-commits/kastree`**. Live testing found a genuine
   **“fix deployed to backend, frontend stuck on stale build”** gap: Railway
   was on `f38f1b1` while www.kastree.ie served a **2h-old** frontend
   (`frontend-rdb82gdcv`, 2026-09-03 23:27) that still rendered object-shaped
   FastAPI `detail` as bare `API 409`. Confirmed reconnected to
   **`infokastree-beep/kastree`** and redeployed (Production deploy hook →
   `frontend-rjwgr0exq` / `ac3bed1` on that org; live Playwright then showed
   the real 409 message + “Open the existing trial balance” link).

   **This is the second distinct time tonight Vercel’s deploy source needed
   manual reconnection.** After any future GitHub-side change (transfer,
   rename, mirror, org move), check Vercel project Settings → Git explicitly
   (the UI/`vercel` equivalent of `git remote -v`) — do **not** assume the
   connected repo followed the GitHub change automatically. Redeploy (or fire
   the Production deploy hook) once the source is confirmed.

   **Automated safeguard (2026-09-04):** every push to `main` runs
   `.github/workflows/verify-production-frontend.yml`, which optionally POSTs
   `VERCEL_DEPLOY_HOOK_URL` and then polls
   `https://www.kastree.ie` for `<meta name="kastree-git-sha">` baked from
   `VERCEL_GIT_COMMIT_SHA` / `GITHUB_SHA`. If the live marker does not match
   the pushed SHA within ~15 minutes, the workflow **fails loudly** (no more
   “detect only if someone remembers to run a script”). Script:
   `scripts/verify_production_frontend_sha.sh`.

3. **Blacknight domain transfer** — `kastree.ie` registration remains under the
   original personal account. Deliberately deferred because .ie registrant
   changes involve ID/passport verification. **Low priority, no functional
   impact** — the domain resolves and serves identically regardless of which
   registrant account holds it.

4. **Google Workspace for `@kastree.ie` (not urgent — professionalism, not
   security)** — Consider setting up Google Workspace on `kastree.ie` so a real
   business mailbox (e.g. `admin@kastree.ie`) can eventually replace
   `infokastree@gmail.com` as the business identity for **GitHub**, **Clerk**,
   and **`PLATFORM_ADMIN_EMAILS`**. `infokastree@gmail.com` is already a
   genuine, dedicated business account (correctly separate from personal email)
   and is **fine to keep using** in the meantime — this is a cosmetic /
   professionalism upgrade, **not** a security fix, and **not urgent**.

   **Deliberately deferred until the business name/brand is fully finalized** —
   trademark search completed, and a decision made on whether to add a **`.ai`**
   domain (currently only `kastree.ie` is owned). Note: `.ai` domains typically
   cost **$70–100+/year**, notably more than the `.ie` domain already secured —
   factor cost into the decision, not just aesthetic appeal. **Revisit Workspace
   and domain decisions together once naming is truly settled, not before.**

   **Requires (when naming is settled):** Google Workspace subscription
   (~$6–7/month); domain verification via a Blacknight DNS record; then the same
   careful transfer process already proven for GitHub/Clerk (confirm old email
   loses access, new email gains it, real evidence at each step — including HTTP
   proof that the old address loses `/admin` and the new one gains it when
   `PLATFORM_ADMIN_EMAILS` changes). **Do as its own focused task when ready**,
   not squeezed into another session’s work.

Longer-term (not tonight’s cutover leftovers): before fundraising, hiring, or
acquisition diligence, fold remaining personal-named ownership into a proper
business entity. That is separate from the items above.

## Clerk workspace — cannot remove original owner after adding business email

Attempted to remove `markdooling25@gmail.com`'s access from the Clerk workspace
after adding `infokastree@gmail.com` as Owner. Clerk blocked this ("won't allow
leaving workspace").

**Likely causes:** `infokastree@gmail.com` may need to fully complete account
setup/verification first, or Clerk may simply require more than one confirmed
owner as a safety measure before allowing the original account to leave.

**Not urgent.** Both accounts currently have Owner access, which is a safe,
working state. Revisit only if genuinely necessary; no risk in leaving both as
members indefinitely.

## Paywall — DONE (2026-09-07)

**Status: complete.** Pricing, client-limit enforcement, Stripe Checkout, and
webhook tier updates are live and proven with a real Stripe test-mode payment.

**Shipped:**

- Pricing page live at `/pricing` (Starter €69/10, Growth €175/30, Practice €349/75).
- Free tier = permanent free (3 clients, no card). Paid upgrades via Checkout.
- Backend gating: `POST /clients` → 403 `CLIENT_LIMIT_REACHED` when over tier cap.
- `POST /billing/checkout` creates Stripe subscription Checkout; webhook remains
  the sole writer of `subscription_tier` / `subscription_status`.
- Railway configured: `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID_STARTER|PRO|SCALE`,
  `STRIPE_WEBHOOK_SECRET`, `FRONTEND_BASE_URL`.
- End-to-end proof (2026-09-07): Upgrade to Starter → Checkout €69 → test card
  `4242…` → `checkout.session.completed` webhook → org `free` → `starter`.

**Earlier Stripe webhook hardening (still relevant):** Two bugs that could
silently drop tier/status updates were fixed in commit `54ec7fe`
(`stripe_service.py`) — unknown Stripe statuses no longer default to
`"active"`, and unmapped `price_id` values log a `WARNING` instead of failing
quietly. Covered by tests in `backend/tests/test_webhooks_api.py`.

**Checkout API version (2026-09-07):** `stripe.api_version` pinned to
`2025-03-31.basil` in `billing.py` so Session.create succeeds on accounts with
Managed Payments (commit `f6a6e40`).

This gap is closed for Product 1 sellability. Remaining billing polish (Customer
Portal, annual plans, invoices UI) is demand-gated — not a blocker.

## Landing page copy — revision brief (high priority)

**Status:** open, **high priority**. Product 1 capability is largely done; the
genuinely open question left is whether the landing page **sells it in five
seconds**. **Do not** ship a half-rewrite in a tired session — revise with a
clear head against this brief. Implementation:
`frontend/components/landing/LandingPage.tsx` (hero, “The problem”, “What you
get”, “How it works”). Related but separate: [Public product demo without
signup](#public-product-demo-without-signup-follow-up) (media) — media does not
fix weak positioning on its own.

### Core principle: the bank-statement-converter benchmark

The revision standard is not “clearer than today.” It is the bar hit by real
solo SaaS products that reach ARR **because the pitch is complete in one
line**. Canonical example: a bank-statement converter whose name *is* the
pitch — **“convert bank statements to Excel.”** No follow-up sentence required.
A stranger understands the product from that alone.

**Kastree’s equivalent single-sentence pitch (source of truth for the hero):**

> Upload a trial balance, get mapped accounts, statements, variance, and AI
> commentary — automatically.

That sentence is the product. The **hero headline must be built around hitting
this exact same immediate-clarity bar**: direct **input → output**, no jargon,
no “platform,” no abstraction, no clever paraphrase that needs decoding. Same
job as “convert bank statements to Excel” — if the headline needs a second
sentence to explain what Kastree does, it has failed.

Supporting lines may add *why* (time saved for accountants) and *how mapping
is special* (AI-assisted, learns per client). They must not be required to
decode the input→output loop; that loop lives in the headline itself.

### The bar: immediately obvious (5 seconds)

Same standard as the best solo-founder SaaS marketing pages (**Bannerbear**,
**Carrd**, **Photopea**) and the bank-statement-converter benchmark above: a
stranger with **zero context** lands on `/` and, within about **five seconds**,
understands (1) exactly what Kastree does and (2) why they’d want it — without
reading secondary sections, without inferring from a feature grid, and without
piecing a story together.

**Immediately obvious** means:

- One clearest possible statement of what happens, front and centre — the
  single-sentence pitch above (or an equally direct paraphrase that still needs
  no follow-up), not a clever abstraction.
- The value is self-evident from that statement (time saved for accountants),
  not deferred to “The problem” further down.
- Anything that makes a first-time visitor **work** to understand the product
  gets cut or demoted below the fold (process lists, stacked jargon, “platform”
  language, combined tiles that hide the differentiator, hedging that softens
  the loop).

Cold-read test: hand the URL to someone who has never heard of Kastree. If they
cannot recite the equivalent of the single-sentence pitch (TB in → mapped
accounts, statements, variance, commentary out — automatically) **and** why
(saves accountants hours of spreadsheet rebuild) after a glance at the first
viewport, the page has failed this brief.

### What’s wrong with the live message today

The page already *mentions* upload, mapping, statements, variance, and
dashboard pieces — but a prospect still has to **assemble** the product from
scattered sections. That fails the five-second / bank-statement-converter bar:

- **Hero** leads with outcome jargon (“Statements, variance, and risk out”)
  rather than a complete input→output sentence like the pitch above. Mapping is
  buried in the supporting sentence (“confirm account mappings”), not named in
  the headline loop.
- **“What you get”** opens with a combined “Upload & map” tile, then spreads
  statements / performance / variance / Ask across a long grid. Mapping is not
  a standout signal; it reads as step 1 of a checklist.
- **“How it works”** is a six-step process list. Fine as depth later; it must
  not be where a stranger first discovers that AI-assisted, per-client mapping
  is a core differentiator — or where they first learn the full output loop.
- **Time saved** is implied (“removes the mechanical steps… not copy-paste”)
  but never stated as the central, concrete reason to care.

Net: informative ≠ immediately obvious. The first viewport must carry the whole
sell; lower sections only deepen or qualify.

### Revision brief (acceptance criteria)

When this is rewritten, the **first viewport alone** must pass the five-second
cold-read test. Primary supporting copy under the hero may reinforce — it must
not be required to understand the product. Specifically:

1. **Hero = the single-sentence pitch (bank-statement-converter bar).**  
   Build the headline around: **Upload a trial balance, get mapped accounts,
   statements, variance, and AI commentary — automatically.** Direct
   input→output only — no jargon, no “platform,” no abstraction. Dashboard /
   performance overview belongs in that same loop (as “dashboard” or equivalent
   plain language) if space allows; risk / Ask / export stay secondary and must
   not replace or obscure the core sentence. If a stranger needs a follow-up
   line to learn what Kastree does, rewrite the headline.

2. **Mapping is a headline capability, not a buried step.**  
   “Mapped accounts” is in the pitch for a reason — keep it explicit among the
   primary outputs, not only as “step 2” of how-it-works. Differentiated signal
   in supporting copy: **AI-assisted account mapping that learns per client**
   (suggestions you confirm; remembered for the next TB). Do not collapse into
   “Upload & map” or leave it only in FAQ.

3. **Time saved for accountants is the why — concrete, central.**  
   The five-second read must include *why they’d want it*: hours not spent
   rebuilding TBs into P&L/BS lines, re-mapping similar client charts, or
   drafting variance notes from a blank sheet. Vague “ready for review” /
   “removes mechanical steps” is colour, not the spine. Answer: *why is
   dropping a TB here faster than Excel today?*

4. **Cut friction for first-time visitors.**  
   Prefer one composition that states the pitch over scavenger-hunt layouts.
   Demote or cut first-viewport copy that forces work: long process lists,
   feature grids that bury the loop, hedging or “platform” language that softens
   the message. Lower sections may qualify (internal review only, human confirms
   mappings, deterministic math) — they must not be the first place the product
   becomes understandable.

### Out of scope for this brief

- Visual redesign / new component library work (unless copy structure forces a
  light layout tweak).
- Pricing, waitlist, or auth flows.
- Demo video / sample company (tracked separately below).
- Inventing capabilities that are not live (do not promise auto-file,
  GL sync, or unattended “push to client”).

### Done when

A zero-context stranger passes the **five-second cold-read test** on the first
viewport alone: the hero hits the bank-statement-converter bar (the
single-sentence pitch, or an equally complete input→output line that needs no
follow-up); *why* (concrete time saved for accountants) is obvious; mapping is
named as a standout; nothing essential requires scrolling or reassembling
sections. Then mark this entry **Resolved** with ship date / commit.

## LinkedIn ads — accountants / fractional CFOs (after hero is live)

**Status:** not started. **Genuinely well-matched** paid channel once the
[landing page hero revision](#landing-page-copy--revision-brief-high-priority)
is live (five-second pitch must be in place first — ads that land on a muddy
hero waste budget).

**Why LinkedIn fits:** job-title and industry targeting reaches accounting
practices and fractional CFOs directly — the same ICP as the eyebrow copy.
Better match than broad search for a niche B2B tool.

**How to run it (when ready):**

- Start with a **small test budget (~€50–100)** to validate click-through and
  signup conversion before scaling. Do not open a large monthly spend on the
  first campaign.
- Target by **job title / industry** (e.g. accountant, practice owner,
  fractional CFO — refine from early click data).
- Creative and landing must match: ads should echo the locked single-sentence
  pitch, not a separate slogan.

**Alongside, not instead of, direct outreach:** LinkedIn ads are a parallel
channel. **Warm outreach to known contacts will likely convert faster** for the
first users. Treat ads as paid validation of the public funnel; treat outreach
as the quicker path to real conversations and early customers. Do both when
promoting — do not wait on ads alone, and do not skip outreach because ads are
running.

## Public product demo without signup (follow-up)

**Status:** not built; not blocking sellability. Complements the
[landing page copy](#landing-page-copy--revision-brief-high-priority) brief —
media does not replace sharper positioning.

Prospects today see a **static** statements-dashboard screenshot on the landing
page. There is no video walkthrough and no public read-only sample company.

**Agreed next step (when a recording exists):** embed a short (60–90s)
screen-recording of a real upload → map → statements → Ask flow on the landing
“How it works” section. A guest/sample-company explorer is deferred (auth/RLS
exceptions + seed maintenance).

## Intake completeness — PDF-TB and GL→TB (Intake Completion Initiative)

**Status:** **Phase 1 (PDF trial balance extraction) = DONE** — built, tested
(clean native-text, messy/imperfect formatting, and OCR-fallback image-only
paths), and safety-proven (mandatory review step confirmed unbypassable via API
and UI). Live on `main` at commit `d01f513` (origin + github; production
frontend SHA match verified).

**What shipped:** Upload “What are you uploading?” → PDF →
`POST /trial-balances/extract-pdf` → editable **Review extracted data** →
confirmed CSV handoff into unchanged `/upload` → mapping/statements pipeline.
Extraction: `pdfplumber` (native-text tables / words) + OCR fallback (PyMuPDF
render + Tesseract). Clean extract never creates a `trial_balances` row;
`/upload` rejects `.pdf` even when extraction would succeed.

**Demand validated (2026-09-08).** Full framing, Phase 1 vs Phase 3 priority,
mapping-not-standalone, and Phase 3 hybrid monetization notes live in
[`product-roadmap.md`](product-roadmap.md) §5 (Intake Completion Initiative).

**Status:** Phase 1 PDF-TB intake **DONE**. Public standalone **Kastree Convert**
(**REMOVED 2026-09-09** — no Solutions nav, no `/solutions/convert`). See
[`solutions-convert-design.md`](solutions-convert-design.md). Subscriber Upload
(PDF-TB + GL→TB) remains the only conversion surface. **Phase 3 (GL → TB): built
in-flow** — [`gl-to-tb-design.md`](gl-to-tb-design.md).

**Surfaces:** Subscriber **Upload-flow** only for PDF-TB and GL→TB. No public
paid Convert product.

The trusted Product 1 engine already starts at a **trial balance**. Practices
do not always have a clean xlsx/csv TB. Two widening steps complete the path
from whatever raw data they have into that same engine:

### 1. PDF trial balance extraction — DONE

**DONE.** Practices can upload a PDF TB, extract (`pdfplumber` + OCR fallback),
review/edit rows, then confirm into the existing parse → map pipeline. Tested
on clean native-text, messy/imperfect formatting, and image-only OCR paths.
Mandatory review is unbypassable: extract creates no TB; `/upload` rejects
`.pdf`; UI only uploads confirmed CSV.

Golden Rule unchanged: extraction yields structured TB rows for deterministic
Python math; fail closed on low confidence.

### 2. General Ledger → Trial Balance (materially bigger — demand confirmed)

**Demand confirmed (2026-09-09)** in the client’s own words (GL dump PDF/Excel →
Excel + TB, quickly). **BUILT** — see [`gl-to-tb-design.md`](gl-to-tb-design.md)
and `POST /trial-balances/convert-gl` (Modes A/B/C, hard balance fail, review
before Upload pipeline). Free in-flow only; Convert stays TB-only.

**This is a MATERIALLY BIGGER undertaking than PDF-TB extraction.** A trial
balance is already summarized and (ideally) balanced. A general ledger is
**raw transaction-level data**. Producing a correct TB from it is closer to a
**bookkeeping / ledger-processing engine** than an intake-format widener — not
“just another upload type.”

**Real complexity is not the summation itself** (bucket-by-code is
straightforward). Correctness around it is the product risk — now specified in
the design draft:

- **Period cutoffs** — inclusive `period_start`…`period_end`; no silent
  inclusion of adjacent dates; excluded counts shown.
- **Opening balance handling** — explicit modes A (OB rows in file), B
  (movements-only; pipeline blocked without prior TB), C (YTD/FY-to-date,
  recommended). Wrong assumption → wrong closing TB; never infer silently.
- **Data validation** — mandatory Σ debit = Σ credit within €0.01 before
  review-confirm; fail closed into no pipeline entry.

**Build shape:** free, in-flow Upload (same as PDF-TB). **Not** standalone
Convert. Phase 1 PDF-TB remains **DONE**.

### Future refinements to the existing GL→TB engine (non-urgent)

Improvements to the **already-built, proven** GL→TB engine — not new products
and not competing work. Revisit only if real client GL data surfaces these as
actual, recurring issues in use.

1. **Duplicate / near-duplicate transaction detection.** Today the engine
   correctly **sums** lines that share an account (by design). Worth adding a
   review flag for suspiciously similar entries (same amount, same date, same
   account) so the user can check before confirm — rather than silently folding
   true duplicates into the TB. Real idea; priority depends on whether client
   GLs commonly contain accidental double-posts.

2. **Multi-currency GL handling.** Confirm current behaviour (engine treats
   amounts as a single functional currency — no FX conversion or per-line
   currency column). If real client ledgers mix currencies in one export,
   decide whether to fail closed, require a currency filter, or support
   conversion. Do not invent multi-currency math until a real case needs it.

3. **Fiscal year vs calendar year period cutoffs.** Period logic is already an
   inclusive `period_start`…`period_end` date window (not hard-coded Jan–Dec),
   so non-calendar fiscal years should work when the user sets those dates
   correctly. Worth an explicit confirmation / regression case (e.g. FY 1 Apr–
   31 Mar) against a real multi-month GL so Mode C YTD/FY-to-date assumptions
   stay trustworthy for non-calendar practices.

## No uptime or error monitoring

**Sentry backend — DONE / CLOSED (2026-09-08):**

- SDK init live: `app/sentry_setup.py` + Railway `SENTRY_DSN` (EU ingest
  `ingest.de.sentry.io`, org slug `kastree`).
- Production deploy `da4e3096…` SUCCESS with commit `9f62c66` on github/main.
- Deliberate prove-out: gated `GET /sentry-debug?token=…` returned **500** with
  `RuntimeError('Sentry deliberate test error — kastree backend verify')` in
  Railway logs; wrong/missing token → **404**.
- Ingest accepted (definitive capture proof): Sentry store API HTTP **200**,
  event id `35d108557805487d9ee3746d5d643045`. Issues UI screenshot / auth
  token **not required**.
- Final lockdown: `SENTRY_DEBUG_TOKEN` **cleared**; `/sentry-debug` with no /
  wrong / empty token returns **404**; `SENTRY_DSN` remains set; `/health` 200.

Still outstanding (separate from Sentry):

- **Uptime alerts** — Railway / Vercel built-in uptime alerts still not enabled.
  Worth enabling before actively promoting the site.

## Statements dashboard — stale-mapping indicator

**Done (2026-09-07):** Statements GET/POST include `mappings_stale` by comparing
`max(account_mappings.updated_at)` for the company against the earliest
`financial_statements.generated_at` for the TB. When true, the Statements page
shows a banner with **Regenerate Statements** (same POST as the header button).

## Performance granularity toggle — built, parked in UI

**Status (2026-09-07):** Monthly / Quarterly / Yearly aggregation is
**implemented and verified** (backend `aggregate_performance_periods`,
`GET .../performance-overview?granularity=`, unit tests for flow-sum vs
stock-last and prior-bucket growth). Live Berkshire proof confirmed correct
math (e.g. Q3 revenue `3910400.00`, cash last-value `93500.00`).

**UI decision:** the Dashboard Monthly/Quarterly/Yearly toggle is **hidden**
for now. With history entirely inside one calendar quarter/year, Quarterly and
Yearly look identical to each other and feel “broken” even though the math is
right. The period dropdown alone is sufficient until real multi-quarter /
multi-year customer data exists.

**Preserve, don’t delete:** keep the endpoint, aggregation service, and tests.
Frontend is locked to `granularity=monthly` with a comment pointing here.
**Re-enable the UI control** once calendar-spanning data would show meaningful
differentiation — no further backend work expected.

## Statement line evidence drill-down (shipped) vs manual override (do not build)

**Shipped (read-only):** click any SOPL/SOFP/SOCIE face line → right slide-over
of contributing TB accounts via
`GET /trial-balances/{tb_id}/statements/lines/{line_id}/sources`
(`source_account_ids` → `account_mappings` + parsed TB rows). Shows account
code, name, and face amount. No editing. Same stacking pattern as Performance
KPI drill-down (exclusive with Copilot).

### Manual override — deliberately NOT surfaced

`statement_line_items` schema already has `is_manual_override`,
`original_amount`, and `overridden_by_user_id`. These fields exist but are
**deliberately not being surfaced or built into any UI/API**.

**Reasoning:** an override, however carefully audited (visible flag, original
value preserved, tracked in Copilot’s evidence pack), still introduces the one
thing every other feature this product was built to prevent — a displayed
statement figure that doesn’t match what the trial balance actually says.
Correct re-mapping already handles the common case of a wrong figure.

**Only revisit** if real practices, using the product with real clients,
demonstrate a genuine, recurring need for a rare, legitimate out-of-system
adjustment that re-mapping cannot solve — not speculatively, based on an unused
schema field.

Also not built (same bar — demand-gated, not speculative):

| Capability | Notes |
|------------|--------|
| Spreadsheet-style formulae / variables | Second calculation engine outside TB → mapping → statements; violates Golden Rule. |
| Add / delete statement lines | Face presentation without TB provenance. |

## Product 2 (statutory reports) — planning notes

Product sequencing lives in [`product-roadmap.md`](product-roadmap.md)
(**Product 2** — Full Statutory Annual Report, Ireland & UK; formerly called
Product 3). Capture hard gates here so they are not treated as optional polish
after build starts. Working-paper / reconciliation evidence is **not** a
separate product — it is a future Product 1 add-on (same internal-review
liability posture).

### Legal gate — “AI-assisted SaaS, not filer/signer of record” (upfront)

**Before any development begins** on full statutory financial statement
production, obtain **real legal counsel** (Ireland/UK) on:

1. Whether framing Kastree as an **“AI-assisted SaaS platform, not the
   filer/signer of record”** is a **legally sufficient** position for this
   specific use case (drafting / assembling statutory-style annual report
   content that could be filed or relied on externally).
2. What **disclaimer and liability structure** would actually be required
   (ToS, UI copy, engagement letters, professional-indemnity boundary) — not
   what sounds reassuring in product docs.
3. How this **differs from Product 1’s settled internal-review-only
   positioning** (including future working-paper / reconciliation add-ons),
   which correctly stays **entirely internal** (no filing / signing surface).
   Product 2 (statutory) is a different liability category; Product 1’s
   internal framing does **not** automatically transfer.

This is a **real, upfront legal gate before building**, not a retrofit after
UI exists. Internal confidence that “just an assistant” sounds reasonable is
**not** confirmed legal grounding — counsel must say so for this use case.

Qualified reviewer sign-off of statutory wording remains pending and still
gates client use. Phase 1 below is schema, the pure engine, and the golden
suite. It produces no client-facing statutory output. Week 2 stores source
files and does not produce statutory output either.

### Nil-line omission rule — reviewer sign-off

The statutory PDF omits a face line or a note breakdown line only when both
the current amount and the comparative are within €0.01 of zero. Net assets,
Total equity, and Profit for the financial year stay even when both are nil.
A first financial period has no comparative column, so a line is omitted only
when the current amount is within €0.01 of zero. The engine still computes
every line. Pending reviewer sign-off.

### Title wording and single-column first period — reviewer sign-off

A period of twelve months is titled "for the year ended <date>". Any other
length is titled "for the period from <start> to <end>". The same phrase is
the heading of each note table. The statement of financial position is
"as at <date>". When the first-financial-period flag is set, the comparative
column is omitted. A later year with a comparative keeps two year columns.
Pending reviewer sign-off.

### Statement order — reviewer sign-off

`findraft/content/frs102-1a-ie/2024.09/pack.json` declares `sections`. The
income statement is order 7 and the statement of financial position is
order 9, with the notes after both. The PDF prints those three in that
declared order. The other ids in the array (cover, contents, other
comprehensive income, changes in equity, cash flow, trading statement) are
not built. The sidebar catalogue stays the hardcoded list. Pending reviewer
sign-off of statement order.

### Share capital particulars — design only

Not built. The share capital note still prints the face amount and
`[share class analysis not recorded]`.

The note needs, for each class: the class name, the number of shares, the
nominal value per share, and both the issued (called-up) position and the
authorised position. Authorised can be blank. Many Irish private companies
have no authorised maximum after the Companies Act 2014, and a blank must
stay "not recorded" or "not applicable" rather than a guessed number.
Issued amount is issued number times nominal value, computed in Python when
the note is built. The form does not ask the user to type that product.

Enter them on the Company details form, in a repeatable share-class block
under the existing Company section, stored on the company. Proposed fields,
none of which exist yet:

- `class_name` — text, for example Ordinary
- `authorised_number` — whole number, optional
- `issued_number` — whole number
- `nominal_value` — money, in the company's functional currency

The note reads those rows. It does not grow a free-text override.

### Week 2 document-type taxonomy — not invented

The v7.6 build plan (§9 Week 2, goal G9) names a **16-type classifier** and
does not list the 16 types. Searches of the specification and the build pack
found the phrase only. Week 2 therefore verifies the real file type
(`pdf`, `xlsx`, `csv`) and does not assign a business-document category.
The category list has to come from the specification before a classifier
of those types can be built.

### Week 4 fixed assets and size eligibility

The journal parser stays cut with GL ingestion. Week 4 stores an immutable
fixed-asset register and builds the movement grid with the engine's
`build_fa_grid`. A re-import creates a new register version. It does not
create a draft; draft creation stays the trial-balance path.

The pinned Irish small pack now carries the size thresholds the specification
states: turnover €15,000,000, balance sheet €7,500,000, 50 employees, 2 of 3,
current year and preceding year. A first financial period is tested on the
current year only. The Irish micro thresholds (€900,000 / €450,000 / 10
employees) are stated in the specification and are not a second pack, so they
are not applied here.

The specification also names an excluded-entity eligibility check and does
not list the excluded categories. That list was not invented. Week 4 applies
the size test only.

### Week 5 mapping exclusions

Product 1 `mapper.py` now applies the FinDraft exclusions: liability, director,
and tax-term names never suggest cash; P&L wording never suggests a
balance-sheet line; statutory heuristic scores stay below 80. A confirmed
prior exact match is the only path to 100. `suggest_statutory_mapping` emits
the pack's engine line names, plus `BANK_OVERDRAFT`, `FA_INTANGIBLE_AMORT`,
and `FA_INTANGIBLE_COST`. Product 1's existing canonical lines are unchanged.

`engine/mapping.aggregate()` stays out of Product 1 statement generation.
The review-queue UI named in the Week 5 build-plan row is not this change.

### Week 13 first practice and the golden suite

Week 13 of the v7.6 §9 plan is the beta: one practice, and a green golden
suite. Goal G10 names roll-forward and report styles for this same week.
That is not the §9 row. Roll-forward is the v1.1 decision (A12). Report
styles are the in-app editing cut. Firm-to-client option inheritance is
Week 14. None of those are built here.

The beta states the standing gate. A qualified reviewer has not signed off
the statutory wording. `wording_signed_off` is false and the response model
cannot say otherwise. The practice records that it will review every output
itself before anything is filed or sent. The record is one append-only audit
row. A second acknowledgement does not add another row. The product does
not file, and it does not produce iXBRL or a CT1.

The numeric gate is the engine suite, run as
`python -m unittest discover -s tests -t .` from `findraft/`. The API does
not report that suite as passed. The test runs it. The first-practice path
uses the Irish pack already built: the golden trial balance, prior year,
confirmed mappings, disclosure answers the practice records, a FINAL
snapshot, the PDF from that snapshot, and one trial-balance evidence
document. Net assets stay 455812.00 and profit stays 157650.00.

The auditor's-report slot, note overrides, text blocks, bank
reconciliation, and the UK pack stay cut.

### Week 12 audit log and erasure

Week 12 states the retention rule and then follows it. Accounting records are
kept for 7 years: the 6-year floor in Companies Act 2014 section 285 and
Taxes Consolidation Act 1997 section 886, plus a 1-year engineering buffer.
The buffer is not a statutory requirement.

An erasure request replaces personal data the practice is not required to
keep. A user's email and login identifier are replaced with a non-identifying
value. A client name becomes `[Redacted Client]`. Company legal names,
director names, and trial-balance account names stay, because they are part
of the accounting record.

Erasure does not delete, and does not rewrite, trial balances, mappings,
drafts, statements, source documents, `archived_records`, or `audit_logs`.
Those records win over the erasure request. An archive keeps its hash and
its `retention_until`. The audit log is append-only: the app role has no
UPDATE or DELETE, a trigger refuses both, and each row carries a `prev_hash`
link. Erasure appends a new row and does not copy the erased name into it.
A name already stored in an earlier archive stays there.

The audit-trail CSV escapes formula-leading `=`, `+`, `-`, and `@`. The
auditor's-report slot, note overrides, and the UK pack stay cut.

### 7-year retention purge (design only)

Not built. Do not add a purge job, a maintenance role, or an append-only
trigger on `archived_records` in the privilege change that revokes `UPDATE`
and `DELETE` from the `findraft` login.

`archived_records.retention_until` is already the calendar date seven years
after the archive (`RETENTION_YEARS = 7` in `backend/app/services/archival.py`,
with 29 February clamped to 28 February). A purge has to delete those rows
after that date. The application login cannot do it once it holds only
`SELECT` and `INSERT` on `archived_records`.

A purge needs all three of the following.

1. A separate maintenance role. It is not the application login and `findraft`
   is not a member of it. An operator job connects as that role, or calls one
   `SECURITY DEFINER` function owned by the table owner. The role is granted
   `DELETE` on `archived_records` and nothing else it does not already need
   to see the expiry date (`SELECT` on that table). It is not granted to the
   web process.

2. Trigger handling. `audit_logs` already has `findraft_audit_log_append_only`,
   which refuses `UPDATE` and `DELETE` even for the table owner. The purge
   does not delete or rewrite audit-log rows. The hash chain stays. There is
   no append-only trigger on `archived_records` today, so a maintenance role
   that holds `DELETE` can remove an expired row. If that trigger is added
   later, it has to allow the owner-owned purge function. A trigger that
   refuses every `DELETE` would make the retention date unenforceable.

3. How `archived_records` is purged. Delete rows whose `retention_until` is
   before the current date. Do not `TRUNCATE`. The `client_id` foreign key is
   `NO ACTION`, so deleting an archive row does not delete the client, and a
   client row that is still there does not block deleting the archive. Do not
   hard-delete the client in order to drop the archive. Product 1 client
   delete and trial-balance delete are soft (`is_deleted` / `deleted_at` plus
   an insert into `archived_records`). They never remove the archive row.
   Write the purge to the operator log. Do not update the archive row to mark
   it purged. `audit_logs`, `subscription_events`, and the other append-only
   tables are not part of this job.

### Week 11 statutory pages and DOCX

Week 11 of the v7.6 §9 plan names a small-company directors' report, the
approval and audit-exemption statements, a compilation report, DOCX export,
and an auditor's-report attachment slot. The slot is the row 13 cut. It is
not built: no placeholder page, no upload, no `draft_attachments` table, and
no generated audit opinion. An unaudited draft carries the audit-exemption
page instead.

The four pages are deterministic. They use the entity record and the profit
figure the statement engine already produced. A missing director, secretary,
principal activity, approval date, practice name, or size test stays missing.
The draft does not invent a section 335 declaration, a section 334 notice,
or a dividend.

Note overrides, text blocks, and report styles stay the in-app editing cut.
DOCX is the export. The Week 8 PDF GET still returns PDF bytes on that
request. The new DOCX path returns a job id. A Postgres worker claims the
job with `FOR UPDATE SKIP LOCKED` and renders in a child process with an
address-space cap and a timeout. Celery and Redis are not added.

A FINAL DOCX is built from the stored snapshot. A later change to the
company record does not change that file. Evidence stays the single
trial-balance document.

### Week 10 adjustments, roles, and locking

The adjustment journal is a balanced set of draft lines the preparer posts
onto the statutory computation. It is not a journal parser, not GL ingestion,
and not a second evidence document. The evidence graph still returns the
single trial-balance source. An adjustment line has no trial-balance row id.
It is a draft input, and the face still has to tie.

Note overrides and text blocks are the in-app editing cut. Those tables are
not created. The lock trigger therefore covers adjustment journals, adjustment
lines, disclosure answers, and confirmed mappings. It does not cover tables
this week refuses to add.

`findraft/web` does not exist. The red/amber/green review state is the
dashboard API. The directors' report and DOCX stay later weeks.

The workspace that calls that API is `/year-ends/{id}/draft`. Generate
statutory draft on the Statements tab opens that address, and opening it
again reloads the year end. When a statutory trial-balance version has been
imported, the page shows the dashboard and posts adjustments, disclosure
answers, and lock through the routes above. Continuing from a Product 1
trial balance inserts one draft row with `tb_version_id` null and leaves
`findraft_tb_versions` empty. That page reloads the adopted pack through
the active draft.

### Statutory workflow — decided, and connected

**Status:** the four connections below are built. A Product 1 trial balance
stays in `trial_balances`. Continuation does not copy it into
`findraft_tb_versions`. FINAL evidence and DOCX stay on the statutory
version path (`evidence_for_version` reads `findraft_tb_lines` and
`source_document_id`; `findraft_render_jobs.tb_version_id` is NOT NULL).

Four decisions:

1. **Page.** Already built. `/year-ends/{id}/draft` is the statutory
   workspace. Generate statutory draft on the Statements tab opens it, and
   the tab links back when a year end already exists for that company and
   period.

2. **Live Product 1 mappings.** Built. The current active draft re-reads
   Product 1 `account_mappings` on each computation, through
   `load_adopted_inputs`. A change made in Product 1 after the draft started
   flows into that active draft. `mappings_sha256` stores the acknowledged
   fingerprint. The page shows a notice when the live set differs, and
   acknowledgement is the only way that notice clears.

3. **Save as you go.** Already built for disclosure answers and
   adjustments, on a draft that already exists. `set_disclosure_answer`
   inserts or updates `findraft_disclosure_answers` and bumps `row_version`
   in the same request. `post_adjustment` inserts the journal and its lines
   the same way. The request session commits. The workspace does not batch
   these into a final submit: Yes and No each POST
   `/drafts/{id}/disclosures` immediately, and Post adjustment POSTs
   `/drafts/{id}/adjustments` for that journal immediately. Reload reads
   them back from the dashboard. On a continuation year end those buttons
   render once `GET /year-ends/{id}/draft` returns the draft row
   continuation inserted. Free-text note
   overrides and text blocks stay the row 13 cut. They are not a third
   save path.

4. **A new draft is a separate report.** Built. Explicitly starting another
   draft for the same trial balance creates a new `DraftVersion` with its
   own id and an empty history. It does not copy the previous draft's
   adjustments or disclosure answers. The previous draft keeps the history
   it already saved, stores `frozen_inputs`, and stops being the active
   live draft. `new_version_from_locked` stays the lock-and-continue path:
   it copies journals and answers forward, and it only starts from a locked
   draft. The new-report action is `POST /drafts/{id}/new-report`.

What this connection does:

- On continuation, insert one `DraftVersion` with `tb_version_id` null.
  A second continuation leaves that row in place. `findraft_tb_versions`
  stays empty.
- `dashboard_for_draft`, `post_adjustment`, `_disclosure_check`, and
  `recompute_draft` read `load_adopted_inputs` when the version id is null.
  `statements_for_adopted` passes that draft's adjustments and disclosure
  flags into the statement builder. A frozen draft reads `frozen_inputs`
  instead of the live Product 1 mappings.
- `mappings_sha256` is the acknowledged fingerprint. The active draft shows
  the notice when the live Product 1 set differs. Acknowledge updates the
  fingerprint. Starting a new report freezes the previous draft so later
  Product 1 edits do not rewrite its history.
- `finalise_draft` still requires a trial-balance version. An adopted draft
  can be worked on and saved. FINAL evidence and DOCX remain out of this
  connection.

When Evidence and DOCX are connected, the statutory draft page
(`/year-ends/{id}/draft`) gets its own export control, separate from the
Statements page export. Word (DOCX), the Week 11 statutory render, is the
primary format accountants use for final review before filing. PDF is a
secondary option. That control is additive to the existing Statements
export. It stays blocked until the render path can read a Product 1 source:
`finalise_draft` still requires a trial-balance version,
`evidence_for_version` reads `findraft_tb_lines` and `source_document_id`,
and `findraft_render_jobs.tb_version_id` is NOT NULL.

### Statutory workspace — one page, one dropdown, in-page sidebar

**Status:** Built 3 October 2026 on the existing `/year-ends/{id}/draft`
page. The in-page sidebar and the five report-setup fields are in the
product. Display rounding, face dates, and column headers are stored on
`findraft_year_ends.report_setup` and are not read by the statement engine.
Cover, accounting policies, notes, and the Form 11 extracts panel are not
built. Form 11 is in the framework catalogue with `available: false`.

**What shipped.** The FRS 102 sidebar is Report setup, Sub-line review,
Disclosures, Adjustments, Review dashboard, Income statement, and Statement
of financial position. The Form 11 catalogue is Report setup, Extracts
summary, and Review dashboard. An unknown framework id is Report setup and
Review dashboard, not the FRS list. Cover, accounting policies, and notes
stay reserved and are not sidebar entries in this build. Statement of
changes in equity is not a sidebar entry in this build.

**Next design, not approved.** A complete set of accounts — section toggles,
company details, cover and directors pages, and the grouped sidebar — is
written in [`statutory-set-of-accounts.md`](statutory-set-of-accounts.md).
That note is design only. Nothing in it is built.

#### One page, one framework dropdown

The statutory draft stays one address, `/year-ends/{id}/draft`, and one
component, `StatutoryDraftWorkspace`. The reporting framework is one
dropdown on that workspace. The same dropdown already sits on the Statements
continuation (`StatutoryContinuation`, `data-testid="statutory-framework"`)
with one built choice: FRS 102 Section 1A (Ireland), pack `frs102-1a-ie` /
`2024.09`. The designed future second choice, still unbuilt, is Sole Trader
/ Form 11 Summary.

Both choices use this page, this year end, and this working draft. A second
route per framework was rejected: it would copy sub-line review, disclosures,
adjustments, and locking, and multiply the bug surface. The dropdown selects
which presentation that draft uses. Disclosure answers, adjustment journals,
and the lock stay on the draft when the dropdown changes. Switching back to
FRS 102 shows the FRS panels again.

Form 11 Summary, when it is built, does not call the FRS 102 pack and does
not invent Section 1A notes. While that choice is selected, the sidebar shows
Report setup, the extracts summary, and the review dashboard. Cover,
accounting policies, the two faces, FRS notes, FRS disclosure questions, and
the seven-line sub-line review stay stored and are hidden for that choice.
Kastree still does not prepare or file Form 11. The practice keys ROS.

Report setup shows the year-end pack pin (`pack_id`, `pack_version`) as the
basis of preparation. Saving report setup does not write that pin. Changing
the pack would change the calculation, so the basis control on this form
does not switch frameworks. The continuation dropdown remains the control
that selects the pack.

#### Sidebar — where each section goes

A left-hand list on the same page, in the spirit of the Accurri section
menu (Report options at the top, then Cover, the statement faces, and Notes).
Choosing an item shows that section. It does not add a route and does not
fork the draft. The address may carry `?section=` so a link opens one
section. The component is still `StatutoryDraftWorkspace`.

The mapping notice, the missing-draft banner, and the first-period gate stay
above the section. They apply whichever section is open.

| Sidebar entry | What is on screen | Where it comes from |
| --- | --- | --- |
| Report setup | The five fields in the next subsection | New. The framework dropdown is the one that already exists |
| Sub-line review | The seven Product 1 lines that need an engine line | Existing `StatutorySublineReview`, when `adopted_trial_balance_id` is set and the framework is FRS 102 |
| Disclosures | Yes / No for each unanswered flag | Existing `data-testid="statutory-disclosures"` |
| Adjustments | Narration, lines, Post adjustment, Lock draft, and the new-report / next-version actions | Existing `statutory-adjustment`, `statutory-lock`, `statutory-new-report`, `statutory-new-version` |
| Review dashboard | Traffic, failed checks, finalise readiness | Existing `statutory-review-dashboard`. This is the section shown when the page opens and a draft exists |
| Income statement | The income face | Existing face table titled Income, inside `statutory-draft-pack` |
| Statement of financial position | The balance-sheet face | Existing face table titled Financial position |
| Notes | Reserved | No workspace panel yet. Week 11 note text stays on the render path. The entry says the note library is not on this page yet |
| Accounting policies | Reserved | Same. No new policy wording |
| Cover | Reserved | Same. Week 11 directors' report, approval, and audit-exemption pages stay render output |

Sub-line review and adjustments are on the sidebar because they are already
on this page. Hiding them would drop the gates the draft already uses. Cover,
accounting policies, and notes are named now so the menu matches the report
the accountant expects. Their panels are not invented in this design.

#### Report setup — the Accurri reference, and the five Kastree fields

The Accurri "Report options" dialog, reviewed on the financial-position face
and on the cash-flow face, is the reference. On that dialog the practice sets
the statement name ("Statement of financial position" or "Balance sheet"),
the current and prior column headers ("as at" on the balance sheet, "ended"
on a period statement, defaulting to the year labels 2024 and 2023), the
currency symbol, and rounding (`Yes - '000`, with the hint "The rounding
used for currency values"). The product's insert-field list also carries
current period start, current period end, and the "as at" and "ended"
headers as separate values. The left menu places Report options above
Sections (Cover, Profit or loss, Balance sheet, Notes).

Kastree takes five fields from that screen. They are presentation. Python
still computes every figure from the trial balance and the draft
adjustments. None of these fields recalculates a number.

1. **Basis of preparation.** The existing reporting-framework dropdown.
   Stored as `year_end.pack_id` and `pack_version`. There is no second
   "basis" field beside it.

2. **Rounding display.** Nearest euro, or nearest €'000. Applied when the
   face is shown and when a draft PDF is rendered. Stored amounts stay
   exact `Decimal`. `findraft/engine/rounding.py` (`flag_for_note`) already
   flags a gap when rounded lines do not add to the rounded total; that
   warning is the behaviour to surface here. Accurri also lets a practice
   type a rounding plug into the chart of accounts. That plug is not this
   field.

3. **Period dates printed on the face.** Current start, current end, prior
   start, prior end. They default from `year_end.period_start`,
   `year_end.period_end`, and the prior trial balance when one is attached.
   A first financial period leaves the prior dates empty. These dates are
   the words on the face. Changing them does not select a different trial
   balance, does not recompute a comparative, and does not move
   `V-GATE-001`. When a printed date differs from the trial-balance date,
   Report setup shows both.

4. **Statement type.** The reference list is audit, review, and compilation.
   Kastree assists the practice and does not file or sign, so the stored
   label is `draft` (today's watermark) or `compilation`. Compilation is the
   one of the three that matches an accountant assembling accounts from the
   client's records, and Week 11 already names a compilation report as a
   deterministic page. Audit is an opinion; the auditor's-report slot stays
   the Week 11 cut. Review, as an assurance conclusion, is the same: Kastree
   does not sign one. The label does not add a signature block, an opinion,
   or a filing step. The small-company audit-exemption page stays the Week
   11 page. It is not an audit engagement type.

5. **Column headers.** Two pairs, as on the Accurri dialog. Statement of
   financial position: a current "as at" header and a prior "as at" header.
   Income statement: a current "ended" header and a prior "ended" header.
   The default text is the year of each display period end. Custom text
   replaces that label. It does not swap which column is current or prior.

**Left on the Accurri dialog, and out of this design.** Consolidation
columns and parent columns ("Show consolidation", "Show parent"). Cash-flow
direct versus indirect. ESG, the strategic report, and budget-versus-actual
comparison headers. "Sign statement of financial position" and any signatory
list. XBRL. Those are separate, larger features. Consolidation, XBRL, and
signatory management stay out of this pass.

### Week 9 statutory evidence graph

A renderable DRAFT can be read as a graph from each face figure back to the
trial-balance accounts that compose it, and from those accounts to the
trial-balance source document. `aggregate().sources` supplies the accounts.
The service checks that they add back to the engine face amount, including
subtotals and the profit and loss account. A graph that does not tie is
withheld.

The chain stops there. The fixed-asset register stays a Week 4 import and a
Week 7 roll-forward input. It is not an evidence-graph node. Journals stay
the row 13 cut.

No new table was added. The graph is computed on the read.

### Week 8 statutory statements

A ready trial balance with an open prior-year gate can be read as a DRAFT
statement of financial position, income statement, and pack notes. Figures
come from `aggregate()`, `build_sofp`, and `build_income_statement`. Note
inclusion is `select_notes`. Rounding gaps are `flag_for_note` at the nearest
whole currency unit. Zero lines stay on the face.

The HTML is Jinja with autoescape on. The PDF passes a `url_fetcher` that
refuses every URL. The watermark is DRAFT. A failed critical check, a closed
gate, an unmapped trial balance, or a `build_sofp` error withholds the
statement and the PDF. Warning checks still render. Useful lives the company
has not supplied stay as placeholders.

No new table was added. FINAL snapshot, the directors' report, DOCX, and
disclosure answers that block FINAL are later weeks. `V-DISC-001` does not
block this DRAFT. Bank reconciliation stays the row 13 cut.

### Week 7 reconciliation v2

Reconciliation now also runs the engine fixed-asset roll-forward, the
comparative check, and the pinned pack's review rules. Comparatives are the
stored prior-year canonical balances rendered by `prior_from_mapped`. A rule
that cannot be evaluated stays CRITICAL. A ready fixed-asset register is the
roll-forward; with no register, a non-zero fixed-asset face fails `V-FA-001`.

Bank reconciliation stays the row 13 cut. `check_bank_reconciliation` is not
called. No new table was added. Review-rule results are computed on the
reconciliation read. They are not stored.

### Week 6 reconciliation v1

Reconciliation runs the engine checks for the trial balance, the balance sheet,
and retained earnings, and calls `build_sofp`, which refuses a non-zero line
the statements do not present. Confirmed mappings are stored per trial-balance
version and are not updated. The prior-year gate still stops the other checks.

FA roll-forward, bank reconciliation, comparatives, and pack review rules are
the Week 7 row. They are not in this change. Bank reconciliation stays the
row 13 cut as a product feature; the engine function is not wired here.

### Week 3 trial-balance ingestion

The four vendor-named parsers (Sage, Xero, QuickBooks, Big Red Book) stay
cut. Week 3 parses with Product 1's generic CSV/XLSX importer, then stores
an immutable trial-balance version. A re-import creates a new draft version.
Prior-year figures are entered as canonical-line amounts, or the year end is
marked as a first financial period. `V-GATE-001` is the engine gate. The
manual entry surface is this API. A second frontend was not added.

### Row 13 scope decision (2026-09-30)

Checklist row 13 of the v7.6 specification is **DECIDED**. Phase 1 proceeds
on Product 1’s mapping suggestions, Clerk auth, and RLS (`app.current_org_id`).

Accepted cuts:

- Four vendor trial-balance parsers. Product 1’s generic CSV/XLSX importer
  already covers the Sage, Xero, and QuickBooks column shapes.
- GL ingestion and evidence-graph depth beyond trial-balance accounts. See
  the deferred note below.
- In-app editing. DOCX export remains the later editing path.
- Bank reconciliation.
- The auditor’s-report attachment slot.
- The UK pack and the full-FRS roadmap.

The pack selector stays **DECIDED** and is not reopened. Billing stays the
row 1 decision: included in existing Kastree tiers.

The beta-practice filing-workflow conversation, including iXBRL and CT1, is a
real-world validation step to hold in parallel with Week 1. It is not a
feature and it does not block Phase 1.

### GL ingestion and evidence-graph depth — deferred

**Status:** deferred. Do not build this speculatively.

Product 1 already converts a general-ledger file into a trial balance
(`backend/app/services/gl_to_tb.py`) and does not keep the transactions.
Persistent journal storage, and a drill-down from a statutory statement
figure through the trial balance to those journals, is a separate capability.
Row 13 drops it from the current build.

Revisit only if a real beta practice specifically asks for transaction-level
drill-down in statutory statements.

The cut is closed. A later week whose natural shape would pass it — another
source document on this graph, a journal, or any node past the trial-balance
account — stops and flags that boundary before any of it is built.

### Model evaluation when Product 2 is scheduled (do not pre-select now)

When Product 2 (statutory report drafting) eventually begins, run a **real,
direct model evaluation at that time** — compare then-current leading models
specifically on the narrow task needed: structured FRS 102 disclosure text
generation and reliable, schema-conformant output.

Do **not** pre-select a model months before the build. The field moves too
fast for an early pick to remain correct. General “computer use” capability is
a different requirement than Product 2 actually has — evaluate the drafting /
schema task, not agentic browsing. Revisit when Product 2 is scheduled, not
before.

## OpenAI Astra (Excel AI assistant) — evaluated, not a Product 1 pivot

**Evaluated:** OpenAI Astra is a general-purpose spreadsheet automation /
editing assistant. It is **not** a domain-specific accounting engine.

It does **not** replace Kastree’s Product 1 core value:

- deterministic statement engine (Python does the math)
- canonical-line mapping with per-client memory
- RLS isolation and audit trail
- automated, provably-correct statement generation from TB

Astra solves a different problem: helping a human edit spreadsheets faster.
Worth evaluating later as a possible **component for Product 2/3**
(statutory report drafting / formatting) **if/when** that work begins and
Astra offers a real API — not a reason to pivot or abandon Product 1.

## External UX / positioning review (high-value, not urgent)

Captured from external review for future consideration. Revisit once Product 1
has real users to validate against — high-value, not urgent.

1. **Trust statement under the heading:** “Nothing is generated until you
   review and confirm the mappings.”
2. **Visual workflow indicator:** Upload → AI Parse → Confirm Mapping →
   Statements → Commentary → Export.
3. **CTA wording reconsideration:** “Parse Trial Balance” vs “Upload and
   Parse”.
4. **Explain the GL option** with one clarifying sentence for first-time
   users.
5. **“Try with demo data” button** — real, worth prioritizing; lowers
   first-upload friction significantly.
6. **Post-parse confidence summary** (“1,286 lines imported, 247 accounts
   detected, balances, 6 need review, ~2 min”) — flagged as the **single
   highest-value** suggestion.
7. **Sharper landing pain-point language** (“turn a 2-hour workflow into 10
   minutes”).
8. **Real social proof once available** (client count, time saved, founder
   credibility — “Built by an ACA Chartered Accountant”).
9. **Explicit “why not just use ChatGPT” differentiation on the landing page**
   — deterministic engine, persistent per-client mapping memory, audit trail,
   RLS isolation — the actual moat, worth stating directly rather than
   assumed.
10. **Long-term positioning reframe worth considering:** “AI Management
    Accounts Analyst” rather than “software.”

