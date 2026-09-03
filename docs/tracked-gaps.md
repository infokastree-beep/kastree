# Tracked gaps

Known implementation gaps that are **accepted for now** but should not be forgotten.
Review this list before claiming a feature area is complete.

For product-level sequencing (three-product roadmap, what to build next vs defer),
see [`product-roadmap.md`](product-roadmap.md).

## Archival write paths

Only **clients** soft-delete currently writes to `archived_records`. See
`backend/app/routers/clients.py` module docstring for detail.

| Entity | Gap |
|--------|-----|
| `trial_balances` | `DELETE /trial-balances/{id}` specified in Product Spec §10.2 / §12.2 (snapshot on delete) — no delete handler or archive write yet. |
| `financial_statements` | `archived_records.entity_type` includes statements, but no delete/archive write path (statements are replaced in place on regenerate; no soft-delete column). |

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

## Equity total — duplicated inline formulas (structural drift risk)

Total-equity calculation has now needed the **same class of fix four separate
times** during this build — `net_assets`, `balance_sheet_balance`, `build_sofp`,
and `build_socie` (`_compute_socie_rollforward`). Each time a new equity concept
was correctly added to one formula but missed in another (most recently
`share_premium` and `revaluation_reserve` on SOFP but not SOCIE).

This is a **structural risk**, not a one-off oversight: four independent inline
formulas that must stay aligned will drift again the next time equity logic
changes.

**Worth considering a genuine refactor:** a single shared
`compute_total_equity(accounts)` (or equivalent) that every call site uses,
rather than four separate sums that can diverge silently until a reconciliation
check fires.

**Not urgent** — each instance has been caught correctly so far — but the pattern
itself is worth fixing at the source **next time equity logic is touched**, rather
than relying on manually catching a fifth instance.

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

**Still deferred** — no data exists to auto-calculate against until a company's
first real upload — but this is the actual target design once built, not a vague
"something better" placeholder.

**Source:** standard audit materiality practice (ISA 320 framework; commonly
cited ranges from professional audit guidance).

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

**Live API today:** `POST /trial-balances/{id}/risk` always passes an empty
history map (`_MVP_HISTORICAL_VARIANCE_PCTS`). Rule 2 therefore **never fires
in production**, monthly or annual, until history is loaded from prior
`variance_analyses` rows. That is documented MVP behaviour in `risk.py`, not a
monthly-specific bug.

**Engine check with monthly-scale % series** (unit tests, history passed in
directly — 2026-09-03):

- 4 prior MoM observations: 20% does **not** flag; 60% **does** (50% bar).
  Sensible for monthly.
- 12 quiet MoM observations (mean ≈ 3.8%, stdev ≈ 3.3%): **15% MoM flags**
  (z ≈ 3.4); 8% does not. Once history is wired, a normal busy month can trip
  the 12+ bucket because MoM noise is tighter than typical YoY swings. Worth a
  real product pass before monthly is a marketed use case — do not retune
  speculatively until history is actually supplied.

Low priority. No production gap beyond the existing empty-history MVP skip.

## Financial statements — currency display (resolved)

Browser dashboard (`StatementsDashboard.tsx`) and export templates (`exporter.py`
Excel/PDF; CSV statement amounts) now show the company's `functional_currency`
and format statement amounts per Cursor Rules §10.7 (comma thousands for GBP/USD,
space for EUR; currency symbol prefix; minus sign for negatives).

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

## Object storage (S3/R2) — not configured in production; exports will fail

**Exports are non-functional in production until this is resolved.**

`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `S3_BUCKET` are listed as
`[REQUIRED for exports]` in `.env.production.example` but have never been set
in the Railway environment. When any export job runs, `boto3` raises
`NoCredentialsError` on the first `put_object` call. The export record lands in
`status="failed"` and the UI shows the error message.

**Fix (three steps, one-time):**

1. Create an S3 bucket (AWS `eu-west-1`) or Cloudflare R2 bucket.
2. Set in Railway service environment:
   - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET`
   - `S3_ENDPOINT_URL` (R2 only: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`)
3. Run once against the bucket to configure 30-day auto-deletion lifecycle:
   `cd backend && python scripts/configure_s3_lifecycle.py`
   (see **R2 lifecycle Admin token** below — **resolved 3 Sep 2026**).

The error message surfaced to the UI when credentials are absent now reads
*"Object storage credentials are not configured…"* (improved from the generic
`"Export job failed unexpectedly"` — commit `030b8fc`+).

> **Note (3 Sep 2026):** Object R/W credentials and the `kastree-exports` bucket
> are live; exports work. Bucket lifecycle for `exports/` is also live (next
> section).

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

**Longer-term deploy plumbing added:** `scripts/trigger_vercel_deploy.sh` (POST
to `VERCEL_DEPLOY_HOOK_URL`) and `.github/workflows/vercel-deploy-hook.yml`
(optional GitHub secret `VERCEL_DEPLOY_HOOK_URL`). Use these once a deploy hook
is configured, then re-run `scripts/verify_security_deploy.sh` until the Vercel
CDN step passes.

**Until the CDN updates:** treat as UI-only — unauthorized users who click Admin
see a blocked API, not cross-tenant data.

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
- **Clerk** — production instance live (`clerk.kastree.ie`); business email has
  Owner access (original owner cannot be removed yet — see section below; safe).
- **Railway (live stack)** — NEW project **overflowing-creation** under
  `infokastree@gmail.com` serves production behind www.kastree.ie; DB migrated;
  RLS re-proven; OLD delightful-purpose left as fallback only.
- **R2 lifecycle** — `exports/` 30-day expiry applied via Admin token (see
  resolved R2 lifecycle section above).
- **Security / cutover** — live API URL, health, soft-delete cleanup, privacy
  policy, Vercel Web Analytics wired and receiving data.

**Genuinely outstanding (complete final list from tonight):**

1. **Vercel project transfer** — still blocked by Vercel’s free **Hobby**-tier
   single-member limit, confirmed multiple times tonight against real docs/UI.
   Completing a transfer to the business account requires upgrading to **Pro**
   (about **$20/month**, at least temporarily) so a shared team can hold both
   members before the transfer finishes. **Not urgent** — production
   (www.kastree.ie) is fully live and working regardless of which account owns
   the Vercel project today (`markdooling25-commits` / kastree team).

2. **Blacknight domain transfer** — `kastree.ie` registration remains under the
   original personal account. Deliberately deferred because .ie registrant
   changes involve ID/passport verification. **Low priority, no functional
   impact** — the domain resolves and serves identically regardless of which
   registrant account holds it.

3. **Railway billing** — the NEW Railway account (`infokastree@gmail.com`,
   project **overflowing-creation**) is on **free trial credit** (earlier
   tonight: on the order of **~$0.11** total usage). **No payment method is on
   file.** When trial credit is exhausted, Railway **pauses** the service (does
   not immediately delete it — data retained ~30 days per Railway’s policy)
   until a card is added. **Action needed:** add a real payment method on that
   NEW account before trial credit runs out, and check remaining balance on
   Railway’s dashboard billing page. This is the only item with a real
   interruption risk if ignored.

Longer-term (not tonight’s cutover leftovers): before fundraising, hiring, or
acquisition diligence, fold remaining personal-named ownership into a proper
business entity. That is separate from the three items above.

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

## No actual paywall — subscription tiers exist in schema only

There is currently **no actual paywall**. Anyone can sign up and gets
unrestricted access at the `"free"` tier indefinitely — no way to see pricing,
no way to pay, and **no code anywhere that checks `subscription_tier` to gate
features**.

**What exists today:**

- Database schema supports tiers (`organisations.subscription_tier`,
  `subscription_status`).
- Stripe webhook correctly updates these fields when Stripe sends real events.

**Stripe tier-update bugs — resolved (2026-09-03):** Two bugs caused tier/status
changes to be silently dropped with no log output:

1. **Unknown Stripe status silently became `"active"`** — `_map_stripe_subscription_status`
   used `mapping.get(stripe_status, "active")` as a fallback. Any unrecognised status
   value (including a future Stripe status or a missing `status` field) overwrote the
   org's real status with `"active"`. An org that was `past_due` could become `"active"`
   without any payment having succeeded. **Fix:** returns `None` for unknown statuses;
   `apply_organisation_billing_update` preserves the existing DB value and logs a
   `WARNING` with the unrecognised status string.

2. **Unmapped `price_id` silently dropped the tier change** — when
   `price_id_to_tier(price_id)` returned `None` (because `STRIPE_PRICE_ID_STARTER/PRO/SCALE`
   env vars are not configured), the tier update was skipped with no log output. A real
   Stripe payment would complete, the org's status would go `active`, but its tier
   would stay on `"free"` forever. **Fix:** logs a `WARNING` with the unmapped
   `price_id` so operators can see exactly which price needs a corresponding env var.

Both fixes are in `backend/app/services/stripe_service.py` (commit `54ec7fe`).
Four new tests in `backend/tests/test_webhooks_api.py` cover both cases and would
have caught these bugs at review time.

**What's missing — all of it:**

1. **Tier policy** — decide what each tier actually restricts (client count? AI
   commentary access? export formats?). Revisit the original spec's rough tier
   table and confirm it is still wanted.
2. **Backend feature gating** — middleware or dependency layer that reads
   `subscription_tier` (and `subscription_status`) and blocks/allows accordingly.
   Never trust the frontend alone for this.
3. **Pricing page** — a real public or authenticated pricing surface on the
   frontend.
4. **Stripe Checkout** — integration so someone can actually pay and land on the
   correct tier.

This is a genuinely separate, substantial piece of work — **not a quick fix**.
Treat it as its own focused session.

**Not urgent** for a waitlist-stage product with no real users yet, but **must
be resolved before onboarding any real, unvetted signups**.

## No uptime or error monitoring

Nothing alerts if `kastree.ie` or the Railway backend goes down, or if the app
throws real errors in production. Right now the only detection path is someone
manually checking.

**Worth adding:**

- **Sentry** (error tracking) — `SENTRY_DSN` is already listed as a supported
  env var in `.env.production.example` but has never been configured.
- **Railway / Vercel built-in uptime alerts** — simpler, no new service; just
  enable in each platform's dashboard.

Low effort, genuinely useful once there are real users. **Not urgent** for a
waitlist-stage product with no signups yet, but should be set up **before
actively promoting the site or onboarding real pilot users**.

## Statements dashboard — no stale-mapping indicator

There is **no visual indicator** when confirmed mappings have changed since
statements were last generated. A user could correct a mapping, forget to click
**Regenerate Statements**, and unknowingly view stale figures.

**Worth adding:** a small banner or prompt on the statements dashboard — e.g.
*"Mappings have changed since these statements were generated — regenerate?"* —
by comparing `account_mappings.updated_at` against
`financial_statements.generated_at` for the same trial balance.

Low effort, real usability improvement. Not a new calculation engine — just a
staleness indicator on top of the existing, correct regenerate-from-scratch
behavior.

