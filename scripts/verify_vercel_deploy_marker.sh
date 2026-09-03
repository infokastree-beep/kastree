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
SITE="${VERCEL_SITE_URL:-https://www.kastree.ie}"
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

is_production_build() {
  python3 - "$FRONTEND" <<'PY'
import json, pathlib, re, sys
frontend = pathlib.Path(sys.argv[1])
manifest_path = frontend / ".next/app-build-manifest.json"
if not manifest_path.exists():
    sys.exit(1)
manifest = json.loads(manifest_path.read_text())
hashed = re.compile(r"-[a-f0-9]{8,}\.js$")
for files in manifest.get("pages", {}).values():
    for f in files:
        if f.startswith("static/chunks/") and hashed.search(f):
            sys.exit(0)
sys.exit(1)
PY
}

find_local_chunk() {
  rg -l --fixed-strings "$MARKER" "$FRONTEND/.next/static/chunks" -g '*-*.js' 2>/dev/null | head -1
}

find_manifest_chunks_with_marker() {
  python3 - "$FRONTEND" "$MARKER" <<'PY'
import json, pathlib, sys
frontend, marker = pathlib.Path(sys.argv[1]), sys.argv[2]
manifest_path = frontend / ".next/app-build-manifest.json"
if not manifest_path.exists():
    sys.exit(0)
manifest = json.loads(manifest_path.read_text())
chunks: set[str] = set()
for files in manifest.get("pages", {}).values():
    for f in files:
        if f.startswith("static/chunks/"):
            chunks.add(f.removeprefix("static/"))
for root, _, files in (frontend / ".next/static/chunks").walk():
    for name in files:
        if not name.endswith(".js") or "-" not in name.rsplit("/", 1)[-1]:
            continue
        path = (root / name).relative_to(frontend / ".next/static")
        try:
            if marker in (root / name).read_text(encoding="utf-8", errors="replace"):
                print(str(path).replace("\\", "/"))
        except OSError:
            pass
PY
}

ensure_build() {
  local existing
  if [[ "$SKIP_BUILD" == "1" ]] && is_production_build; then
    existing="$(find_local_chunk || true)"
    if [[ -n "$existing" ]]; then
      echo "Using existing frontend build ($existing)"
      return 0
    fi
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
  local status
  status="$(curl -sSL -o /tmp/vercel_chunk_body.txt -w '%{http_code}' "$url" 2>/dev/null || true)"
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

scan_cdn_for_marker() {
  echo "Fallback: scanning discoverable Vercel CDN chunks for '$MARKER' ..."
  python3 - "$SITE" "$MARKER" <<'PY'
import re, sys, urllib.request
from collections import deque

site, marker = sys.argv[1], sys.argv[2]

def fetch(path: str) -> str:
    url = site + path if path.startswith("/") else site + "/" + path
    with urllib.request.urlopen(url, timeout=20) as resp:
        return resp.read().decode("utf-8", "replace")

pages = ["/", "/sign-in"]
queue: deque[str] = deque()
seen: set[str] = set()
for page in pages:
    try:
        html = fetch(page)
    except Exception:
        continue
    for path in re.findall(r"/_next/static/chunks/[^\"']+?\.js", html):
        if path not in seen:
            seen.add(path)
            queue.append(path)

found = None
while queue:
    path = queue.popleft()
    try:
        body = fetch(path)
    except Exception:
        continue
    if marker in body:
        found = path
        break
    for ref in re.findall(r"/_next/static/chunks/[^\"']+?\.js", body):
        if ref not in seen:
            seen.add(ref)
            queue.append(ref)
    for ref in re.findall(r"\"static/chunks/([^\"']+?\.js)\"", body):
        full = f"/_next/static/chunks/{ref}"
        if full not in seen:
            seen.add(full)
            queue.append(full)

if found:
    print(f"OK: found marker in {found} (scanned {len(seen)} chunks)")
    sys.exit(0)
print(f"FAIL: marker not found in {len(seen)} discoverable CDN chunks", file=sys.stderr)
sys.exit(1)
PY
}

discover_live_layout_chunks() {
  python3 - "$SITE" <<'PY'
import re, sys, urllib.request

site = sys.argv[1].rstrip("/")
req = urllib.request.Request(site + "/", headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")

seen: set[str] = set()

# Script tags on the page often include the current root app layout chunk.
for path in re.findall(r"/_next/static/chunks/app/layout-[a-f0-9]+\.js", html):
    rel = path.removeprefix("/_next/static/")
    if rel not in seen:
        seen.add(rel)
        print(rel)

# App Router flight data can also contain escaped static/chunks references.
for rel in re.findall(r"static/chunks/app/layout-[a-f0-9]+\.js", html):
    normalized = rel.removeprefix("static/")
    if normalized not in seen:
        seen.add(normalized)
        print(normalized)
PY
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

  local live_tried=0
  while IFS= read -r rel; do
    [[ -z "$rel" ]] && continue
    url="$(chunk_url "$rel")"
    echo "Checking Vercel CDN using live HTML-resolved layout chunk ..."
    echo "  live chunk: $rel"
    live_tried=1
    if verify_chunk_at_url "$url" "chunk: $rel"; then
      return 0
    fi
    echo ""
  done < <(discover_live_layout_chunks)

  if [[ "$live_tried" == "1" ]]; then
    scan_cdn_for_marker
    return
  fi

  ensure_build
  local tried=0
  while IFS= read -r rel; do
    [[ -z "$rel" ]] && continue
    url="$(chunk_url "$rel")"
    echo "Checking Vercel CDN for marker '$MARKER' ..."
    echo "  local chunk: $rel"
    tried=1
    if verify_chunk_at_url "$url" "chunk: $rel"; then
      return 0
    fi
    echo ""
  done < <(find_manifest_chunks_with_marker)

  if [[ "$tried" == "0" ]]; then
    local_chunk="$(find_local_chunk || true)"
    if [[ -z "$local_chunk" ]]; then
      echo "FAIL: marker '$MARKER' not found in local frontend build output" >&2
      exit 1
    fi
    rel="${local_chunk#"$FRONTEND/.next/static/"}"
    url="$(chunk_url "$rel")"
    echo "Checking Vercel CDN for marker '$MARKER' ..."
    echo "  local chunk: $rel"
    if verify_chunk_at_url "$url" "chunk: $rel"; then
      return 0
    fi
    echo ""
  fi

  scan_cdn_for_marker
}

main
