#!/usr/bin/env bash
# Poll the live production frontend until it serves the expected git SHA.
#
# The frontend embeds <meta name="kastree-git-sha" content="<sha>"> via
# NEXT_PUBLIC_GIT_SHA / VERCEL_GIT_COMMIT_SHA (see frontend/next.config.mjs and
# app/layout.tsx). This script is the automated safeguard that Vercel actually
# published the commit we pushed — not a manual "remember to check" step.
#
# Usage:
#   ./scripts/verify_production_frontend_sha.sh <expected-sha>
#   EXPECTED_SHA=abc123 ./scripts/verify_production_frontend_sha.sh
#
# Environment:
#   VERCEL_SITE_URL           default https://www.kastree.ie
#   VERIFY_TIMEOUT_SECONDS    default 900 (15 min — covers Vercel build+alias)
#   VERIFY_POLL_SECONDS       default 20
#   VERIFY_INITIAL_DELAY_SECONDS  default 45 (let deploy hook / git build start)
#
set -euo pipefail

EXPECTED="${1:-${EXPECTED_SHA:-}}"
SITE="${VERCEL_SITE_URL:-https://www.kastree.ie}"
SITE="${SITE%/}"
TIMEOUT="${VERIFY_TIMEOUT_SECONDS:-900}"
POLL="${VERIFY_POLL_SECONDS:-20}"
INITIAL_DELAY="${VERIFY_INITIAL_DELAY_SECONDS:-45}"

if [[ -z "$EXPECTED" ]]; then
  echo "Usage: $0 <expected-full-or-short-sha>" >&2
  exit 2
fi

# Normalise to lowercase hex; accept full or unique prefix (min 7).
EXPECTED="$(echo "$EXPECTED" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
if [[ ! "$EXPECTED" =~ ^[0-9a-f]{7,40}$ ]]; then
  echo "FAIL: expected SHA looks invalid: $EXPECTED" >&2
  exit 2
fi

fetch_live_sha() {
  # Prefer meta tag; fall back to scanning HTML for the baked env string.
  python3 - "$SITE" <<'PY'
import re, sys, urllib.request

site = sys.argv[1].rstrip("/")
req = urllib.request.Request(
    site + "/",
    headers={
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "User-Agent": "kastree-verify-production-frontend-sha/1.0",
    },
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", "replace")
except Exception as exc:
    print(f"ERROR:{exc}", file=sys.stderr)
    sys.exit(3)

# Next.js metadata.other → <meta name="kastree-git-sha" content="...">
m = re.search(
    r'<meta\s+name=["\']kastree-git-sha["\']\s+content=["\']([0-9a-fA-F]{7,40}|dev)["\']',
    html,
    re.I,
)
if m:
    print(m.group(1).lower())
    sys.exit(0)

# Fallback: content property order sometimes differs
m = re.search(
    r'<meta\s+content=["\']([0-9a-fA-F]{7,40}|dev)["\']\s+name=["\']kastree-git-sha["\']',
    html,
    re.I,
)
if m:
    print(m.group(1).lower())
    sys.exit(0)

print("MISSING", file=sys.stderr)
sys.exit(4)
PY
}

sha_matches() {
  local live="$1"
  [[ "$live" == "$EXPECTED" ]] && return 0
  # Prefix match either way (full vs short)
  [[ "$live" == "$EXPECTED"* ]] && return 0
  [[ "$EXPECTED" == "$live"* ]] && return 0
  return 1
}

echo "Verifying production frontend serves commit $EXPECTED"
echo "  site:    $SITE"
echo "  timeout: ${TIMEOUT}s  poll: ${POLL}s  initial delay: ${INITIAL_DELAY}s"
echo ""

if [[ "$INITIAL_DELAY" -gt 0 ]]; then
  echo "Waiting ${INITIAL_DELAY}s for Vercel build to start ..."
  sleep "$INITIAL_DELAY"
fi

deadline=$((SECONDS + TIMEOUT))
attempt=0
last_live=""

while (( SECONDS < deadline )); do
  attempt=$((attempt + 1))
  set +e
  live="$(fetch_live_sha 2>/tmp/verify_frontend_sha_err.txt)"
  rc=$?
  set -e
  err="$(cat /tmp/verify_frontend_sha_err.txt 2>/dev/null || true)"

  if [[ "$rc" -eq 0 && -n "$live" ]]; then
    last_live="$live"
    echo "attempt $attempt: live kastree-git-sha=$live"
    if sha_matches "$live"; then
      echo ""
      echo "OK: www production frontend is serving $live (matches expected $EXPECTED)"
      exit 0
    fi
  else
    echo "attempt $attempt: could not read live SHA (rc=$rc) ${err}"
  fi

  remaining=$((deadline - SECONDS))
  if (( remaining <= 0 )); then
    break
  fi
  sleep_for=$POLL
  if (( sleep_for > remaining )); then
    sleep_for=$remaining
  fi
  sleep "$sleep_for"
done

echo "" >&2
echo "FAIL: production frontend did NOT serve expected commit within ${TIMEOUT}s" >&2
echo "  expected: $EXPECTED" >&2
echo "  live:     ${last_live:-<unreadable>}" >&2
echo "  site:     $SITE" >&2
echo "" >&2
echo "Likely causes:" >&2
echo "  - Vercel Git source not pointed at this GitHub repo (check Settings → Git)" >&2
echo "  - Deploy hook / auto-deploy did not fire" >&2
echo "  - Build failed or is still running — check Vercel dashboard" >&2
echo "  - CDN still serving previous deployment alias" >&2
echo "" >&2
echo "::error title=Production frontend SHA mismatch::www.kastree.ie serves '${last_live:-unreadable}' but push expected '$EXPECTED'" >&2
exit 1
