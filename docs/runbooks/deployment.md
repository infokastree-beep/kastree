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

## Frontend CORS (browser → API)

Browser calls hit FastAPI directly at `NEXT_PUBLIC_API_BASE_URL`. Set backend `CORS_ORIGINS` to the frontend origin(s), comma-separated (default includes `http://127.0.0.1:43123` and `http://localhost:43123`). No wildcards in production (Product Spec §12).

For Clerk session JWTs, set `CLERK_PUBLISHABLE_KEY` (or `CLERK_JWKS_URL`) on the API so RS256 verification works; local tests continue to use HS256 `AUTH_JWT_SECRET`.
