#!/usr/bin/env bash
# Provision the findraft app role (superuser) and verify RLS enforcement.
#
# Prerequisites:
#   - DATABASE_URL_SYNC set to the Railway *postgres superuser* URL
#   - alembic upgrade head already applied (tables exist)
#
# Usage:
#   export DATABASE_URL_SYNC='postgresql://postgres:...@host:port/railway'
#   ./backend/scripts/provision_and_verify_findraft_role.sh
#
# Outputs:
#   - Generated password (save securely)
#   - findraft DATABASE_URL_SYNC / DATABASE_URL for Railway backend service vars
#   - RLS verification query output (must show 0 client rows with fake org)

set -euo pipefail

if [[ -z "${DATABASE_URL_SYNC:-}" ]]; then
  echo "ERROR: DATABASE_URL_SYNC must be set to the superuser connection URL." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Railway default database name; override if needed.
DATABASE_NAME="${DATABASE_NAME:-railway}"

if [[ -z "${FINDRAFT_PASSWORD:-}" ]]; then
  FINDRAFT_PASSWORD="$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)"
fi

echo "=== Provisioning findraft role on database: ${DATABASE_NAME} ==="
psql "$DATABASE_URL_SYNC" \
  -v "findraft_password=${FINDRAFT_PASSWORD}" \
  -v "database_name=${DATABASE_NAME}" \
  -f "$SCRIPT_DIR/provision_findraft_app_role.sql"

# Build findraft connection URLs from superuser URL (replace user/password).
FINDRAFT_SYNC_URL="$(
  python3 - <<'PY' "$DATABASE_URL_SYNC" "$FINDRAFT_PASSWORD"
import sys
from urllib.parse import quote, urlparse, urlunparse

raw = sys.argv[1].replace("postgresql+asyncpg://", "postgresql://")
password = quote(sys.argv[2], safe="")
user = quote("findraft", safe="")
url = urlparse(raw)
host = url.hostname or "localhost"
port = f":{url.port}" if url.port else ""
netloc = f"{user}:{password}@{host}{port}"
print(urlunparse((url.scheme, netloc, url.path or "/railway", "", "", "")))
PY
)"

FINDRAFT_ASYNC_URL="${FINDRAFT_SYNC_URL/postgresql:\/\//postgresql+asyncpg:\/\/}"

echo ""
echo "=== findraft connection strings (set on Railway BACKEND service) ==="
echo "DATABASE_URL_SYNC=${FINDRAFT_SYNC_URL}"
echo "DATABASE_URL=${FINDRAFT_ASYNC_URL}"
echo ""
echo "=== RLS verification (as findraft, fake org → expect 0 rows) ==="
psql "$FINDRAFT_SYNC_URL" -f "$SCRIPT_DIR/verify_findraft_rls.sql"

echo ""
echo "Save FINDRAFT_PASSWORD securely. Keep the postgres superuser URL separate for migrations/bootstrap only."
