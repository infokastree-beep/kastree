#!/usr/bin/env bash
# Confirm a string exists in a live Vercel CDN chunk (post-deploy frontend smoke check).
#
# Resolves the chunk path by building the frontend at the current commit (same hash
# Vercel should publish for that commit), then fetches the chunk from production CDN.
# A "successful" Vercel deploy is not enough — this checks the marker is actually served.
#
# Example (after platform-admin nav fix):
#   ./scripts/verify_vercel_deploy_marker.sh is_platform_admin
#
# Environment:
#   VERCEL_SITE_URL     Production site (default: https://kastree.ie)
#   VERCEL_SKIP_BUILD=1 Skip npm run build when .next already contains the marker
#   VERCEL_VERIFY_CHUNK Relative path under _next/static/ (skip local build lookup)
#
set -euo pipefail

MARKER="${1:-}"
SITE="${VERCEL_SITE_URL:-https://kastree.ie}"
SITE="${SITE%/}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND="$ROOT/frontend"
SKIP_BUILD="${VERCEL_SKIP_BUILD:-0}"

if [[ -z "$MARKER" ]]; then
  echo "Usage: $0 <marker-string>" >&2
  echo "  Builds frontend (unless VERCEL_SKIP_BUILD=1), finds the chunk containing" >&2
  echo "  MARKER, and verifies the same chunk path on the live Vercel CDN." >&2
  exit 2
fi

find_local_chunk() {
  rg -l --fixed-strings "$MARKER" "$FRONTEND/.next/static/chunks" -g '*.js' 2>/dev/null | head -1
}

ensure_build() {
  local existing
  existing="$(find_local_chunk || true)"
  if [[ "$SKIP_BUILD" == "1" && -n "$existing" ]]; then
    echo "Using existing frontend build ($existing)"
    return 0
  fi
  echo "Building frontend to resolve CDN chunk path for marker '$MARKER' ..."
  (cd "$FRONTEND" && npm run build --silent)
}

chunk_url() {
  local rel="$1"
  local encoded
  encoded="$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1], safe='/'))" "$rel")"
  echo "$SITE/_next/static/$encoded"
}

verify_chunk_at_url() {
  local url="$1"
  local label="$2"
  local status body
  status="$(curl -sS -o /tmp/vercel_chunk_body.txt -w '%{http_code}' "$url" || true)"
  body="$(cat /tmp/vercel_chunk_body.txt 2>/dev/null || true)"
  if [[ "$status" == "200" ]] && grep -qF "$MARKER" /tmp/vercel_chunk_body.txt; then
    echo "OK: live CDN chunk contains '$MARKER'"
    echo "  $label"
    echo "  url: $url"
    return 0
  fi
  echo "FAIL: live CDN chunk does NOT contain '$MARKER'" >&2
  echo "  $label" >&2
  echo "  url: $url" >&2
  echo "  HTTP: $status" >&2
  return 1
}

main() {
  local rel local_chunk url

  if [[ -n "${VERCEL_VERIFY_CHUNK:-}" ]]; then
    rel="${VERCEL_VERIFY_CHUNK#_next/static/}"
    rel="${rel#/}"
    url="$(chunk_url "$rel")"
    echo "Checking Vercel CDN (VERCEL_VERIFY_CHUNK) for marker '$MARKER' ..."
    verify_chunk_at_url "$url" "chunk: $rel"
    return
  fi

  ensure_build
  local_chunk="$(find_local_chunk || true)"
  if [[ -z "$local_chunk" ]]; then
    echo "FAIL: marker '$MARKER' not found in local frontend build output" >&2
    echo "Run: cd frontend && npm run build" >&2
    exit 1
  fi

  rel="${local_chunk#"$FRONTEND/.next/static/"}"
  url="$(chunk_url "$rel")"
  echo "Checking Vercel CDN for marker '$MARKER' ..."
  echo "  local chunk: $rel"
  verify_chunk_at_url "$url" "chunk: $rel"
}

main
