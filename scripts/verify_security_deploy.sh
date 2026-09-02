#!/usr/bin/env bash
# Post-security-change checklist: remotes in sync + live Railway + Vercel markers.
#
# Usage:
#   ./scripts/verify_security_deploy.sh
#   ./scripts/verify_security_deploy.sh --require-commit 3686d9a --marker is_platform_admin
#
# With --marker, checks BOTH:
#   - Railway backend source (require_platform_admin in admin.py by default)
#   - Vercel frontend CDN chunk (is_platform_admin in built dashboard layout chunk)
#
# Override backend marker file or frontend-only/backend-only via env:
#   RAILWAY_VERIFY_FILE=/app/app/routers/users.py
#   VERCEL_SKIP_BUILD=1
#
set -euo pipefail

REQUIRE_COMMIT=""
MARKER=""
RAILWAY_MARKER=""
VERCEL_MARKER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --require-commit)
      REQUIRE_COMMIT="${2:-}"
      shift 2
      ;;
    --marker)
      MARKER="${2:-}"
      shift 2
      ;;
    --railway-marker)
      RAILWAY_MARKER="${2:-}"
      shift 2
      ;;
    --vercel-marker)
      VERCEL_MARKER="${2:-}"
      shift 2
      ;;
    -h|--help)
      sed -n '2,16p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -n "$MARKER" ]]; then
  RAILWAY_MARKER="${RAILWAY_MARKER:-$MARKER}"
  VERCEL_MARKER="${VERCEL_MARKER:-$MARKER}"
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SYNC_ARGS=()
if [[ -n "$REQUIRE_COMMIT" ]]; then
  SYNC_ARGS+=(--require-commit "$REQUIRE_COMMIT")
fi

echo "=== Step 1: verify origin/main == github/main ==="
"$ROOT/scripts/verify_remotes_in_sync.sh" "${SYNC_ARGS[@]}"

if [[ -n "$RAILWAY_MARKER" ]]; then
  echo ""
  echo "=== Step 2: verify live Railway backend ==="
  "$ROOT/scripts/verify_railway_deploy_marker.sh" "$RAILWAY_MARKER"
fi

if [[ -n "$VERCEL_MARKER" ]]; then
  echo ""
  echo "=== Step 3: verify live Vercel frontend CDN ==="
  VERCEL_SKIP_BUILD="${VERCEL_SKIP_BUILD:-1}" "$ROOT/scripts/verify_vercel_deploy_marker.sh" "$VERCEL_MARKER"
fi

echo ""
echo "All security deploy checks passed."
