# Tracked gaps

Known implementation gaps that are **accepted for now** but should not be forgotten.
Review this list before claiming a feature area is complete.

For product-level sequencing (three-product roadmap, what to build next vs defer),
see [`product-roadmap.md`](product-roadmap.md).

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

### The bar: immediately obvious (5 seconds)

Same standard as the best solo-founder SaaS marketing pages (**Bannerbear**,
**Carrd**, **Photopea**): a stranger with **zero context** lands on `/` and,
within about **five seconds**, understands (1) exactly what Kastree does and
(2) why they’d want it — without reading secondary sections, without inferring
from a feature grid, and without piecing a story together.

**Immediately obvious** means:

- One clearest possible statement of what happens, front and centre — not a
  clever paraphrase.
- The value is self-evident from that statement (time saved for accountants),
  not deferred to “The problem” further down.
- Anything that makes a first-time visitor **work** to understand the product
  gets cut or demoted below the fold (process lists, stacked jargon, combined
  tiles that hide the differentiator, hedging that softens the loop).

Cold-read test: hand the URL to someone who has never heard of Kastree. If they
cannot say “drop a trial balance in → get mapping, statements, variance,
dashboard, and commentary out — and it saves accountants hours of spreadsheet
rebuild” after a glance at the first viewport, the page has failed this brief.

### What’s wrong with the live message today

The page already *mentions* upload, mapping, statements, variance, and
dashboard pieces — but a prospect still has to **assemble** the product from
scattered sections. That fails the five-second bar:

- **Hero** leads with outcome jargon (“Statements, variance, and risk out”)
  rather than the single clearest action (“drop your trial balance in”). Mapping
  is buried in the supporting sentence (“confirm account mappings”), not named
  as a headline capability.
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

1. **One clearest statement of what happens.**  
   Lead with the concrete action: **drop your trial balance in** (.xlsx / .csv).
   In the same breath (headline + one short line), name the full automatic
   chain — no inference required: **mapping → statements (SOPL / SOFP / SOCIE)
   → variance → dashboard / performance overview → AI commentary**. Risk flags,
   Ask, and export stay secondary; they must not crowd or replace this loop in
   the hero.

2. **Mapping is a headline capability, not a buried step.**  
   Name it **explicitly** among the primary things the product does — alongside
   statements / variance / dashboard — not only as “step 2” of how-it-works.
   Differentiated signal in plain language: **AI-assisted account mapping that
   learns per client** (suggestions you confirm; remembered for the next TB).
   Do not collapse into “Upload & map” or leave it only in FAQ.

3. **Time saved for accountants is the why — concrete, central.**  
   The five-second read must include *why they’d want it*: hours not spent
   rebuilding TBs into P&L/BS lines, re-mapping similar client charts, or
   drafting variance notes from a blank sheet. Vague “ready for review” /
   “removes mechanical steps” is colour, not the spine. Answer: *why is
   dropping a TB here faster than Excel today?*

4. **Cut friction for first-time visitors.**  
   Prefer one composition that states TB in → outputs out over scavenger-hunt
   layouts. Demote or cut first-viewport copy that forces work: long process
   lists, feature grids that bury the loop, hedging that softens the message.
   Lower sections may qualify (internal review only, human confirms mappings,
   deterministic math) — they must not be the first place the product becomes
   understandable.

### Out of scope for this brief

- Visual redesign / new component library work (unless copy structure forces a
  light layout tweak).
- Pricing, waitlist, or auth flows.
- Demo video / sample company (tracked separately below).
- Inventing capabilities that are not live (do not promise auto-file,
  GL sync, or unattended “push to client”).

### Done when

A zero-context stranger passes the **five-second cold-read test** on the first
viewport alone: what happens (TB → mapping + statements + variance + dashboard
+ commentary) and why (concrete time saved for accountants) are immediately
obvious; mapping is named as a standout; nothing essential requires scrolling
or reassembling sections. Then mark this entry **Resolved** with ship date /
commit.

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

