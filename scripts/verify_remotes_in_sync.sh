#!/usr/bin/env bash
# Fail if origin/main and github/main point at different commits.
#
# Railway deploys from GitHub (markdooling25-commits/kastree). Cloud Agent sessions
# often push to origin (Cursor) first. Pushing only to origin leaves production on
# stale code even when Railway env vars change and redeploy.
#
# Run after every security-relevant commit, before claiming a fix is live:
#   ./scripts/verify_remotes_in_sync.sh
#   ./scripts/verify_remotes_in_sync.sh --require-commit f6cb675
#
set -euo pipefail

REQUIRE_COMMIT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --require-commit)
      REQUIRE_COMMIT="${2:-}"
      shift 2
      ;;
    -h|--help)
      sed -n '2,12p' "$0"
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

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "ERROR: remote 'origin' is not configured" >&2
  exit 1
fi

if ! git remote get-url github >/dev/null 2>&1; then
  echo "ERROR: remote 'github' is not configured (Railway deploy source)" >&2
  echo "Add: git remote add github git@github.com:markdooling25-commits/kastree.git" >&2
  exit 1
fi

echo "Fetching origin and github..."
git fetch origin main --quiet
git fetch github main --quiet

ORIGIN_SHA="$(git rev-parse origin/main)"
GITHUB_SHA="$(git rev-parse github/main)"

echo "origin/main : $ORIGIN_SHA $(git log -1 --format='%s' origin/main)"
echo "github/main : $GITHUB_SHA $(git log -1 --format='%s' github/main)"

if [[ "$ORIGIN_SHA" != "$GITHUB_SHA" ]]; then
  echo "" >&2
  echo "FAIL: origin/main and github/main are OUT OF SYNC." >&2
  echo "Railway deploys from github — production may be running older code." >&2
  echo "Fix: git push github main" >&2
  exit 1
fi

if [[ -n "$REQUIRE_COMMIT" ]]; then
  if ! git merge-base --is-ancestor "$REQUIRE_COMMIT" github/main; then
    echo "" >&2
    echo "FAIL: github/main does not contain required commit $REQUIRE_COMMIT" >&2
    exit 1
  fi
  echo "OK: github/main contains required commit $REQUIRE_COMMIT"
fi

echo "OK: origin/main and github/main are in sync ($ORIGIN_SHA)"
