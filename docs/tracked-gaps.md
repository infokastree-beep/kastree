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

## Trial balance uploads — local disk, not S3

TB files are written to `settings.upload_dir` (env: `UPLOAD_DIR`, default
`/tmp/findraft-uploads`) via `file://` paths in `trial_balances.file_url`.
Export files already use S3/R2 (`backend/app/services/exporter.py`).

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

**Not Google OAuth-specific** — affects all sign-up paths when email is missing
from the org webhook payload.

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

All infrastructure accounts (GitHub, Vercel, Railway, Clerk, Blacknight) are
currently owned by a **personal email**, not a dedicated business entity.

**Fine to defer for now.** Before any serious fundraising, hiring, or acquisition
conversation, these should be transferred to a business-owned account (and
eventually a properly incorporated company). Investors and acquirers routinely
check this in due diligence — org ownership, billing, domain registrar, and
who holds production secrets.

**Not urgent now.** Track for when FinDraft moves beyond solo early-access.

## No actual paywall — subscription tiers exist in schema only

There is currently **no actual paywall**. Anyone can sign up and gets
unrestricted access at the `"free"` tier indefinitely — no way to see pricing,
no way to pay, and **no code anywhere that checks `subscription_tier` to gate
features**.

**What exists today:**

- Database schema supports tiers (`organisations.subscription_tier`,
  `subscription_status`).
- Stripe webhook correctly updates these fields when Stripe sends real events
  (once the separately-tracked tier-update bug is fixed).

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

