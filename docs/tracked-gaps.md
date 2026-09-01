# Tracked gaps

Known implementation gaps that are **accepted for now** but should not be forgotten.
Review this list before claiming a feature area is complete.

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

**Not a bug — a scope question for a future session.** Review against real
client trial balances (not synthetic test data) before deciding whether to expand
the canonical set. If expanded, scope the downstream changes: Statement Builder
line placement, validator rules, frontend dropdown/constants, and LLM tie-breaker
prompts must stay aligned.

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
profile**. Real accounting practice bases materiality on a percentage of a
relevant benchmark — profit before tax, revenue, or total assets, chosen based
on the company's situation — not a fixed number.

**Worth building:** auto-suggested thresholds derived from the company's own
first uploaded trial balance (e.g. 5% of profit before tax, falling back to 1% of
total assets if profit is small or negative), recalculated as new periods come
in, with **manual override always available**.

**Not urgent.** Static defaults are a reasonable MVP starting point since there
is no data to benchmark against before a first upload exists — but a real,
valuable improvement once there is usage data to validate against.

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

## Waitlist signups — no authenticated way to view signups

`POST /waitlist` is public (rate-limited per IP, unique email constraint). Rows
live in `waitlist_signups` with **INSERT-only RLS** for the `findraft` app role
(`FORCE ROW LEVEL SECURITY` + single `FOR INSERT` policy — no SELECT/UPDATE/DELETE
policies, so ORM queries cannot read PII).

**There is no authenticated endpoint or dashboard to list signups.** The only way
to see who joined today is direct DB access (superuser/psql against production
Postgres). The app role cannot SELECT these rows by design.

**Missing (low effort):** a simple admin-only `GET /waitlist` to list signups,
role-gated to **Owner** only (same `require_roles("owner")` pattern as
`GET /organisations/me/archived-records`). That route will also need a read path
past INSERT-only RLS (e.g. a `SECURITY DEFINER` function or a dedicated SELECT
policy scoped to an admin check). Until that exists, the waitlist is not
practically useful for following up with signups without manual DB access.

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

