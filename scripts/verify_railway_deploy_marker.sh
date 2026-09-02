#!/usr/bin/env bash
# Confirm a string exists in live Railway backend source (post-deploy smoke check).
#
# Example (after platform-admin fix):
#   ./scripts/verify_railway_deploy_marker.sh require_platform_admin
#
set -euo pipefail

MARKER="${1:-}"
SERVICE="${RAILWAY_SERVICE:-kastree}"
FILE_PATH="${RAILWAY_VERIFY_FILE:-/app/app/routers/admin.py}"

if [[ -z "$MARKER" ]]; then
  echo "Usage: $0 <marker-string> [service]" >&2
  echo "  Checks that FILE_PATH on the live Railway container contains MARKER." >&2
  exit 2
fi

if ! command -v railway >/dev/null 2>&1; then
  echo "ERROR: railway CLI not installed" >&2
  exit 1
fi

echo "Checking Railway service '$SERVICE' for marker '$MARKER' in $FILE_PATH ..."
if railway ssh -s "$SERVICE" "grep -q '$MARKER' '$FILE_PATH'"; then
  echo "OK: live container contains '$MARKER'"
else
  echo "FAIL: live container does NOT contain '$MARKER' in $FILE_PATH" >&2
  echo "Production may still be on pre-fix code. Push github/main and wait for deploy." >&2
  exit 1
fi
