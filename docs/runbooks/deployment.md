# Deployment Runbook

## Pre-launch checklist (object storage)

Terraform under `terraform/` is Month 2+ (Cursor Rules §4). Until IaC owns the
bucket, run these steps once per environment after the S3/R2 bucket exists.

### Export file retention (Product Spec §12.2 / §12.6)

Generated Excel/PDF/CSV files must expire after **30 days**. Deletion is
enforced only by a **bucket-level lifecycle configuration** — not by
`put_object(Expires=...)` (that sets an HTTP caching header only) and not by
application-level deletion logic.

1. Configure the lifecycle rule (idempotent; safe to re-run):

   ```bash
   cd backend
   python scripts/configure_s3_lifecycle.py
   # or: python -m scripts.configure_s3_lifecycle
   ```

   The script merges a rule (`findraft-exports-expire-30d`) that:
   - Filters on prefix `exports/` **and** tag `retention=export-30d`
   - Sets `Expiration.Days` to `export_file_ttl_days` (default 30)

2. **Verify on the real bucket** (unit tests against a mocked S3 client cannot
   prove objects are deleted):

   ```bash
   aws s3api get-bucket-lifecycle-configuration --bucket "$S3_BUCKET"
   ```

   Confirm the rule is `Enabled`, matches `exports/` + the retention tag, and
   `Expiration.Days` is `30`.

3. Application uploads (`S3ObjectStorage.put_export`) must continue to set
   `Tagging=retention=export-30d` so the tag filter matches. `Expires=` on
   put is optional (caching hint only) and must not be treated as retention.

If a download is requested after the object is gone, the exporter regenerates
from retained statement data in Postgres (`regenerate_export_if_missing`).

---

## Pre-launch checklist (Postgres — Stripe webhook RLS lookup)

`/webhooks/stripe` resolves `organisations.id` from `stripe_customer_id` /
`stripe_subscription_id` via SECURITY DEFINER functions owned by
`findraft_rls_bypass` (`NOLOGIN` + `BYPASSRLS`). That role **cannot** be
created through the normal `findraft`-role Alembic migration path
(`CREATE ROLE … BYPASSRLS` needs a superuser / `CREATEROLE` connection).

Run this once per environment (fresh staging, new prod DB, disaster-recovery
restore) **before** or immediately after applying migration `c3d4e5f6a7b8`.
Skipping it leaves Stripe webhooks failing at org-lookup with an opaque error.

1. Apply the bootstrap script as a database superuser (idempotent):

   ```bash
   # Local / self-hosted Postgres:
   sudo -u postgres psql -d findraft_dev \
     -f backend/scripts/bootstrap_stripe_rls_lookup.sql

   # Hosted Postgres (use the provider superuser / admin URL):
   psql "$DATABASE_SUPERUSER_URL" \
     -f backend/scripts/bootstrap_stripe_rls_lookup.sql
   ```

2. Verify:

   ```bash
   psql "$DATABASE_URL" -c "\df app_find_org_id_for_stripe*"
   psql "$DATABASE_URL" -c \
     "SELECT rolname, rolbypassrls FROM pg_roles WHERE rolname = 'findraft_rls_bypass';"
   ```

3. Then run normal app migrations as `findraft` (policy restore + bootstrap check):

   ```bash
   cd backend && alembic upgrade head
   ```

### EXECUTE grant tradeoff (conscious choice)

`GRANT EXECUTE` on `app_find_org_id_for_stripe_customer` /
`app_find_org_id_for_stripe_subscription` goes to the **general `findraft`
role**, not a webhook-specific role. That is a deliberate, accepted tradeoff:
the functions only ever return a single `uuid` via exact-match lookup on a
high-entropy Stripe ID, so the practical risk of other `findraft`-role code
paths calling them is low — but it **is** a wider grant than strictly
necessary. A future reviewer should treat that as an intentional decision, not
an oversight. (Same note sits above the `GRANT EXECUTE` lines in
`backend/scripts/bootstrap_stripe_rls_lookup.sql`.)

Do **not** reintroduce a permissive `organisations` SELECT policy gated on a
session GUC (an earlier draft did; it was caught in review and rejected).

## Backend deploy (Railway)

Production backend is configured via **`railway.toml`** at the repo root (Docker
build from `infra/docker/Dockerfile.backend`, health check `/health`, `$PORT`
binding). Prefer Railway over Render for the short-term TB upload volume path
(`UPLOAD_DIR=/data/uploads` on a mounted volume). See `.env.production.example`
for every env var.

### Migrations

`backend/alembic/env.py` reads **`DATABASE_URL_SYNC`** from the environment and
falls back to `sqlalchemy.url` in `alembic.ini` for local dev. In production,
set `DATABASE_URL_SYNC` on the host and run:

```bash
cd backend && alembic upgrade head
```

Never rely on the alembic.ini localhost URL in staging/production.

### Application database role (`findraft`) — required before deploy

The running API **must not** use Railway's default `postgres` superuser
connection. Superuser sessions bypass RLS unconditionally, which silently
disables every org-isolation policy.

Run **once per environment**, as the database superuser, **after**
`alembic upgrade head` (tables must exist for `GRANT ALL ON ALL TABLES`):

```bash
# Railway shell: DATABASE_URL_SYNC is the linked Postgres superuser URL.
export DATABASE_URL_SYNC='postgresql://postgres:...@host:port/railway'
./backend/scripts/provision_and_verify_findraft_role.sh
```

The role name **must** be `findraft` — `bootstrap_stripe_rls_lookup.sql`
already grants `EXECUTE` on Stripe org-lookup functions to that role.

Then set the **backend service** env vars (not the Postgres plugin) to the
script's `findraft` URLs:

- `DATABASE_URL` — `postgresql+asyncpg://findraft:…`
- `DATABASE_URL_SYNC` — `postgresql://findraft:…`

Keep the original `postgres` superuser URL in a separate secret (e.g.
`DATABASE_SUPERUSER_URL`) for one-off admin only: Stripe RLS bootstrap,
Alembic migrations, and re-running this provision script. **Never** point the
running app at the superuser connection.

**Verify RLS before deploy** (script runs this automatically; re-run manually
any time):

```bash
psql "$FINDRAFT_DATABASE_URL_SYNC" -f backend/scripts/verify_findraft_rls.sql
```

With `app.current_org_id` set to a fake UUID, `SELECT count(*) FROM clients`
must return **0**. A superuser connection would return all rows — that means
RLS is not enforced and the app must not go live.

## Frontend CORS (browser → API)

Browser calls hit FastAPI directly at `NEXT_PUBLIC_API_BASE_URL`. Set backend `CORS_ORIGINS` to the frontend origin(s), comma-separated (default includes `http://127.0.0.1:43123` and `http://localhost:43123`). No wildcards in production (Product Spec §12).

For Clerk session JWTs, set `CLERK_PUBLISHABLE_KEY` (or `CLERK_JWKS_URL`) on the API so RS256 verification works; local tests continue to use HS256 `AUTH_JWT_SECRET`.

### Clerk browser origin (Sign in / widget)

The Clerk JS SDK only initializes when the page **Origin** matches an allowed domain on your Clerk application. If the script tag loads (`clerk.kastree.ie`) but the header **Sign in** link or `/sign-in` widget never appears, open the browser console — a common error is:

`Invalid HTTP Origin header — The Request HTTP Origin header must be equal to or a subdomain of the requesting URL.`

**Fix:** In the [Clerk Dashboard](https://dashboard.clerk.com) → your production instance → **Domains**, add every frontend origin you deploy to (e.g. `https://frontend-ten-flame-18.vercel.app` for Vercel preview, and `https://kastree.ie` / `https://www.kastree.ie` for production). Redeploy is not required after adding domains; refresh the browser.

Vercel env vars for the frontend (Production):

| Variable | Notes |
|----------|--------|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | `pk_live_…` for the same Clerk instance as the backend |
| `CLERK_SECRET_KEY` | `sk_live_…` — server/middleware only |
| `NEXT_PUBLIC_CLERK_READY` | Must be exactly `true` |
| `CLERK_TRUST_HOST` | `true` on Vercel (required for middleware) |
| `NEXT_PUBLIC_API_BASE_URL` | `https://kastree-production.up.railway.app` |

After changing any `NEXT_PUBLIC_*` variable, trigger a new Vercel deployment so the value is baked into the client bundle.

## Local / dev backend process

Run **one** uvicorn instance per environment during dev and testing (e.g. `uvicorn app.main:app --reload` on a single port); a second process without `--reload` will serve stale code and write confusing validation or statement results while the reloaded instance has the fix.
