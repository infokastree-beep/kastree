#!/usr/bin/env bash
# Post-security-change checklist: remotes in sync + optional live Railway marker.
#
# Usage:
#   ./scripts/verify_security_deploy.sh
#   ./scripts/verify_security_deploy.sh --require-commit f6cb675 --marker require_platform_admin
#
set -euo pipefail

REQUIRE_COMMIT=""
MARKER=""

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
    -h|--help)
      sed -n '2,8p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SYNC_ARGS=()
if [[ -n "$REQUIRE_COMMIT" ]]; then
  SYNC_ARGS+=(--require-commit "$REQUIRE_COMMIT")
fi

echo "=== Step 1: verify origin/main == github/main ==="
"$ROOT/scripts/verify_remotes_in_sync.sh" "${SYNC_ARGS[@]}"

if [[ -n "$MARKER" ]]; then
  echo ""
  echo "=== Step 2: verify live Railway container ==="
  "$ROOT/scripts/verify_railway_deploy_marker.sh" "$MARKER"
fi

echo ""
echo "All security deploy checks passed."
