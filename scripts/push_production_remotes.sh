#!/usr/bin/env bash
# Push the current branch to BOTH remotes that matter for production.
#
# Cloud Agent / Cursor sessions default `origin` to Cursor's git host.
# Railway + Vercel auto-deploy from GitHub (`github` remote =
# infokastree-beep/kastree). Pushing only to origin leaves production on a
# stale SHA — this bit us twice (Admin nav CDN, then materiality / Delete
# company). Vercel auto-deploy itself is fine; the GitHub ref never moved.
#
# Usage:
#   ./scripts/push_production_remotes.sh
#   ./scripts/push_production_remotes.sh --verify-live   # also poll www.kastree.ie
#
set -euo pipefail

VERIFY_LIVE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --verify-live) VERIFY_LIVE=1; shift ;;
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

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: not inside a git repository" >&2
  exit 1
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$BRANCH" == "HEAD" ]]; then
  echo "ERROR: detached HEAD — check out main (or a named branch) first" >&2
  exit 1
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "ERROR: remote 'origin' is not configured" >&2
  exit 1
fi
if ! git remote get-url github >/dev/null 2>&1; then
  echo "ERROR: remote 'github' is not configured (Vercel/Railway deploy source)" >&2
  echo "Add: git remote add github git@github.com:infokastree-beep/kastree.git" >&2
  exit 1
fi

SHA="$(git rev-parse HEAD)"
echo "Pushing $BRANCH ($SHA) to origin and github ..."
git push -u origin "HEAD:refs/heads/$BRANCH"
git push -u github "HEAD:refs/heads/$BRANCH"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ "$BRANCH" == "main" ]]; then
  "$ROOT/scripts/verify_remotes_in_sync.sh" --require-commit "$SHA"
else
  echo "NOTE: not on main — skipped verify_remotes_in_sync.sh (main-only)."
fi

if [[ "$VERIFY_LIVE" -eq 1 ]]; then
  if [[ "$BRANCH" != "main" ]]; then
    echo "ERROR: --verify-live only makes sense on main (production tracks main)" >&2
    exit 1
  fi
  echo ""
  echo "Polling production frontend for SHA $SHA ..."
  VERIFY_INITIAL_DELAY_SECONDS="${VERIFY_INITIAL_DELAY_SECONDS:-45}" \
    "$ROOT/scripts/verify_production_frontend_sha.sh" "$SHA"
fi

echo ""
echo "OK: pushed to origin + github ($SHA)"
