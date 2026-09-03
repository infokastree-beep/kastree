#!/usr/bin/env bash
# Trigger a Vercel production redeploy via Deploy Hook URL.
#
# Create in Vercel: Project → Settings → Git → Deploy Hooks → Production → main
# Export the hook URL (do not commit it):
#   export VERCEL_DEPLOY_HOOK_URL='https://api.vercel.com/v1/integrations/deploy/...'
#
# Usage:
#   ./scripts/trigger_vercel_deploy.sh
#
set -euo pipefail

HOOK="${VERCEL_DEPLOY_HOOK_URL:-}"
if [[ -z "$HOOK" ]]; then
  echo "VERCEL_DEPLOY_HOOK_URL is not set." >&2
  echo "Create a Production deploy hook in Vercel (Settings → Git → Deploy Hooks)" >&2
  echo "and export the URL, then re-run this script." >&2
  exit 1
fi

echo "Triggering Vercel production deploy via deploy hook ..."
status="$(curl -sSL -o /tmp/vercel_hook_response.json -w '%{http_code}' -X POST "$HOOK")"
if [[ "$status" =~ ^2 ]]; then
  echo "OK: deploy hook accepted (HTTP $status)"
  cat /tmp/vercel_hook_response.json
  echo ""
  exit 0
fi

echo "FAIL: deploy hook returned HTTP $status" >&2
cat /tmp/vercel_hook_response.json >&2
exit 1
