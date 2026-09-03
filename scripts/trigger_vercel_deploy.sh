#!/usr/bin/env bash
# Trigger a Vercel production redeploy via Deploy Hook URL and optionally wait.
#
# Create in Vercel: Project → Settings → Git → Deploy Hooks → Production → main
# Export the hook URL (do not commit it):
#   export VERCEL_DEPLOY_HOOK_URL='https://api.vercel.com/v1/integrations/deploy/...'
#
# Optional:
#   VERCEL_TOKEN          List/poll deployment status via Vercel REST API
#   VERCEL_POLL_TIMEOUT   Seconds to wait for READY (default: 900)
#   VERCEL_SKIP_POLL=1    Trigger only; do not wait
#
# Usage:
#   ./scripts/trigger_vercel_deploy.sh
#
set -euo pipefail

HOOK="${VERCEL_DEPLOY_HOOK_URL:-}"
POLL_TIMEOUT="${VERCEL_POLL_TIMEOUT:-900}"
SKIP_POLL="${VERCEL_SKIP_POLL:-0}"
RESPONSE_FILE="/tmp/vercel_hook_response.json"
STATE_FILE="/tmp/vercel_deploy_state.json"

if [[ -z "$HOOK" ]]; then
  echo "VERCEL_DEPLOY_HOOK_URL is not set." >&2
  echo "Create a Production deploy hook in Vercel (Settings → Git → Deploy Hooks)" >&2
  echo "and export the URL, then re-run this script." >&2
  exit 1
fi

hook_project_id() {
  python3 - "$HOOK" <<'PY'
import sys
parts = sys.argv[1].rstrip("/").split("/")
for i, part in enumerate(parts):
    if part == "deploy" and i + 2 < len(parts):
        print(parts[i + 1])
        break
PY
}

hook_deploy_id() {
  python3 - "$HOOK" <<'PY'
import sys
print(sys.argv[1].rstrip("/").split("/")[-1])
PY
}

echo "Triggering Vercel production deploy via deploy hook ..."
status="$(curl -sSL -o "$RESPONSE_FILE" -w '%{http_code}' -X POST "$HOOK")"
if [[ ! "$status" =~ ^2 ]]; then
  echo "FAIL: deploy hook returned HTTP $status" >&2
  cat "$RESPONSE_FILE" >&2
  exit 1
fi

echo "OK: deploy hook accepted (HTTP $status)"
cat "$RESPONSE_FILE"
echo ""

JOB_ID="$(python3 - "$RESPONSE_FILE" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
print(data.get("job", {}).get("id", ""))
PY
)"
JOB_CREATED_MS="$(python3 - "$RESPONSE_FILE" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
print(data.get("job", {}).get("createdAt", ""))
PY
)"
PROJECT_ID="$(hook_project_id)"
DEPLOY_HOOK_ID="$(hook_deploy_id)"

python3 - "$JOB_ID" "$JOB_CREATED_MS" "$PROJECT_ID" "$DEPLOY_HOOK_ID" <<'PY' >"$STATE_FILE"
import json, sys
job_id, created_ms, project_id, hook_id = sys.argv[1:5]
json.dump({
    "jobId": job_id,
    "jobCreatedAtMs": int(created_ms) if created_ms else None,
    "projectId": project_id,
    "deployHookId": hook_id,
    "deploymentId": None,
}, sys.stdout)
PY

echo "Parsed hook response:"
echo "  jobId: ${JOB_ID:-<missing>}"
echo "  jobCreatedAtMs: ${JOB_CREATED_MS:-<missing>}"
echo "  projectId: ${PROJECT_ID:-<missing>}"
echo "  deployHookId: ${DEPLOY_HOOK_ID:-<missing>}"

if [[ "$SKIP_POLL" == "1" ]]; then
  exit 0
fi

if [[ -z "${VERCEL_TOKEN:-}" ]]; then
  echo ""
  echo "VERCEL_TOKEN not set — polling production CDN for is_platform_admin (up to ${POLL_TIMEOUT}s) ..."
  ROOT="$(cd "$(dirname "$0")/.." && pwd)"
  deadline=$((SECONDS + POLL_TIMEOUT))
  while (( SECONDS < deadline )); do
    if VERCEL_SKIP_BUILD=1 "$ROOT/scripts/verify_vercel_deploy_marker.sh" is_platform_admin >/tmp/vercel_poll.log 2>&1; then
      cat /tmp/vercel_poll.log
      echo "Deployment appears live on CDN."
      exit 0
    fi
    echo "  still waiting ($(date -u +%H:%M:%S)) ..."
    sleep 20
  done
  echo "TIMEOUT: CDN marker not live after ${POLL_TIMEOUT}s" >&2
  tail -20 /tmp/vercel_poll.log >&2 || true
  exit 1
fi

echo ""
echo "Polling Vercel API for deployment created by this hook (up to ${POLL_TIMEOUT}s) ..."
deadline=$((SECONDS + POLL_TIMEOUT))
DEPLOYMENT_ID=""
while (( SECONDS < deadline )); do
  since_ms=$((JOB_CREATED_MS - 5000))
  api_url="https://api.vercel.com/v6/deployments?projectId=${PROJECT_ID}&limit=5&since=${since_ms}"
  curl -sSL -H "Authorization: Bearer ${VERCEL_TOKEN}" "$api_url" -o /tmp/vercel_deployments.json
  DEPLOYMENT_ID="$(python3 - /tmp/vercel_deployments.json "$DEPLOY_HOOK_ID" "$JOB_CREATED_MS" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
hook_id, created_ms = sys.argv[2], int(sys.argv[3])
for dep in data.get("deployments", []):
    meta = dep.get("meta") or {}
    if meta.get("deployHookId") == hook_id or dep.get("created", 0) >= created_ms:
        print(dep.get("uid", ""))
        break
PY
)"
  if [[ -n "$DEPLOYMENT_ID" ]]; then
    break
  fi
  sleep 10
done

if [[ -z "$DEPLOYMENT_ID" ]]; then
  echo "FAIL: could not find deployment for hook job ${JOB_ID}" >&2
  exit 1
fi

python3 - "$STATE_FILE" "$DEPLOYMENT_ID" <<'PY'
import json, sys
path, dep_id = sys.argv[1], sys.argv[2]
state = json.load(open(path))
state["deploymentId"] = dep_id
json.dump(state, open(path, "w"))
PY

echo "Found deployment: ${DEPLOYMENT_ID}"

deadline=$((SECONDS + POLL_TIMEOUT))
while (( SECONDS < deadline )); do
  curl -sSL -H "Authorization: Bearer ${VERCEL_TOKEN}" \
    "https://api.vercel.com/v13/deployments/${DEPLOYMENT_ID}" \
    -o /tmp/vercel_deployment.json
  python3 - /tmp/vercel_deployment.json <<'PY'
import json, sys
dep = json.load(open(sys.argv[1]))
meta = dep.get("meta") or {}
git = dep.get("gitSource") or {}
print(f"deploymentId: {dep.get('id') or dep.get('uid')}")
print(f"readyState: {dep.get('readyState') or dep.get('state')}")
print(f"url: {dep.get('url')}")
sha = meta.get("githubCommitSha") or git.get("sha") or meta.get("gitlabCommitSha") or ""
ref = meta.get("githubCommitRef") or git.get("ref") or ""
msg = meta.get("githubCommitMessage") or meta.get("gitlabCommitMessage") or ""
print(f"commit: {sha}")
print(f"ref: {ref}")
if msg:
    print(f"message: {msg.splitlines()[0]}")
ready = dep.get("readyState") or dep.get("state") or ""
if ready in {"READY", "ERROR", "CANCELED"}:
    sys.exit(0 if ready == "READY" else 1)
sys.exit(2)
PY
  poll_status=$?
  if [[ "$poll_status" == "0" ]]; then
    echo "Deployment ${DEPLOYMENT_ID} is READY."
    exit 0
  elif [[ "$poll_status" != "2" ]]; then
    echo "Deployment ${DEPLOYMENT_ID} failed." >&2
    exit 1
  fi
  sleep 15
done

echo "TIMEOUT waiting for deployment ${DEPLOYMENT_ID}" >&2
exit 1
