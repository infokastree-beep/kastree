#!/usr/bin/env bash
# Cloud Agent install script for FinDraft (Kastree).
#
# Idempotent, non-interactive setup of the full dev stack:
#   - system packages (PostgreSQL + WeasyPrint runtime libs + Python venv/pip)
#   - a local PostgreSQL cluster with the `findraft` role + `findraft_dev` DB
#   - the backend Python virtualenv and pinned dependencies
#   - the Alembic schema (staged so the superuser-only Stripe RLS bootstrap
#     runs between migration a1b2c3d4e5f6 and head, per docs/runbooks/deployment.md)
#   - the frontend node_modules
#   - local-only .env files (gitignored) if they do not already exist
#
# The `findraft` role is created as a NON-superuser, NON-bypassrls LOGIN role
# that OWNS the findraft_dev database. This mirrors the documented production
# security model (docs/runbooks/deployment.md + backend/scripts/
# provision_findraft_app_role.sql + backend/scripts/verify_findraft_rls.sql):
# the running app must NOT connect as a superuser, because a superuser session
# bypasses every org-isolation RLS policy unconditionally. Owning the tables lets
# findraft run the Alembic migrations (including the data migrations that
# `ALTER TABLE ... DISABLE ROW LEVEL SECURITY` for backfills), while FORCE ROW
# LEVEL SECURITY still applies the policies to the owner at runtime — so the
# app is subject to RLS exactly as in production. install verifies this at the
# end via verify_findraft_rls.sql (fake org -> 0 client rows).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> [1/7] Installing system packages"
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -qq
sudo apt-get install -y -qq \
  postgresql postgresql-contrib \
  python3-venv python3-pip \
  libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
  libffi-dev shared-mime-info \
  tesseract-ocr tesseract-ocr-eng

# Detect the installed PostgreSQL major version (e.g. 16).
PG_VER="$(ls /usr/lib/postgresql/ | sort -n | tail -1)"

echo "==> [2/7] Starting PostgreSQL ${PG_VER}"
sudo pg_ctlcluster "$PG_VER" main start 2>/dev/null || true
# Wait for the socket to accept connections.
for _ in $(seq 1 30); do
  if sudo -u postgres pg_isready -q; then break; fi
  sleep 1
done

echo "==> [3/7] Ensuring findraft role and findraft_dev database"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'findraft') THEN
    CREATE ROLE findraft LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'local';
  ELSE
    ALTER ROLE findraft LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'local';
  END IF;
END
$$;
SQL
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='findraft_dev'" | grep -q 1; then
  sudo -u postgres createdb -O findraft findraft_dev
fi

echo "==> [4/7] Backend virtualenv + dependencies"
cd "$REPO_ROOT/backend"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -q -r requirements.txt

echo "==> [5/7] Database migrations (staged around the RLS bootstrap)"
export DATABASE_URL_SYNC="postgresql://findraft:local@localhost/findraft_dev"
# A throwaway org GUC lets the data migrations evaluate FORCE-RLS policies even
# if findraft is ever provisioned as a non-superuser; a superuser ignores it.
export PGOPTIONS="-c app.current_org_id=00000000-0000-0000-0000-000000000000"
# 1) Create the base tables (organisations, ...).
.venv/bin/alembic upgrade a1b2c3d4e5f6
# 2) Superuser-only Stripe webhook RLS lookup role + SECURITY DEFINER functions.
sudo -u postgres psql -v ON_ERROR_STOP=1 -d findraft_dev \
  -f "$REPO_ROOT/backend/scripts/bootstrap_stripe_rls_lookup.sql"
# 3) Apply the remaining migrations.
.venv/bin/alembic upgrade head

# 4) Verify RLS is actually enforced for the findraft app role. With a fake org
#    GUC, clients must return 0 rows; a superuser/bypassrls connection would
#    return all rows (docs/runbooks/deployment.md). Fail install if not enforced.
echo "==> Verifying findraft RLS enforcement"
unset PGOPTIONS
PGPASSWORD=local psql -h localhost -U findraft -d findraft_dev -v ON_ERROR_STOP=1 \
  -f "$REPO_ROOT/backend/scripts/verify_findraft_rls.sql"

echo "==> [6/7] Frontend dependencies"
cd "$REPO_ROOT/frontend"
npm ci

echo "==> [7/7] Local env files (created only if missing; gitignored)"
BACKEND_ENV="$REPO_ROOT/backend/.env"
if [ ! -f "$BACKEND_ENV" ]; then
  cat > "$BACKEND_ENV" <<'ENV'
APP_ENV=development
APP_VERSION=0.1.0
DATABASE_URL=postgresql+asyncpg://findraft:local@localhost/findraft_dev
DATABASE_URL_SYNC=postgresql://findraft:local@localhost/findraft_dev
CORS_ORIGINS=http://127.0.0.1:43123,http://localhost:43123
UPLOAD_DIR=/tmp/findraft-uploads
ENV
fi
mkdir -p /tmp/findraft-uploads
FRONTEND_ENV="$REPO_ROOT/frontend/.env.local"
if [ ! -f "$FRONTEND_ENV" ]; then
  cat > "$FRONTEND_ENV" <<'ENV'
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
# Clerk auth is off until real keys are provided; dashboard routes redirect to /.
NEXT_PUBLIC_CLERK_READY=false
ENV
fi

echo "==> install complete"
