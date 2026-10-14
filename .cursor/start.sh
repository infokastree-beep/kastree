#!/usr/bin/env bash
# Cloud Agent start script for FinDraft (Kastree).
#
# Runs on every boot. Brings up PostgreSQL (its process does not survive
# across boots even when the data dir is snapshotted), waits until it accepts
# connections, then starts the API and Next.js dev server in tmux. Schema and
# dependency setup live in install.sh, never here.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PG_VER="$(ls /usr/lib/postgresql/ 2>/dev/null | sort -n | tail -1)"
if [ -n "${PG_VER:-}" ]; then
  sudo pg_ctlcluster "$PG_VER" main start 2>/dev/null || true
  for _ in $(seq 1 30); do
    if sudo -u postgres pg_isready -q; then break; fi
    sleep 1
  done
  if ! sudo -u postgres pg_isready -q; then
    echo "PostgreSQL did not become ready" >&2
    exit 1
  fi
fi

mkdir -p /tmp/findraft-uploads

if ! tmux has-session -t backend 2>/dev/null; then
  tmux new-session -d -s backend -c "$REPO_ROOT/backend" -- bash -lc \
    "PYTHONPATH='$REPO_ROOT' OPENAI_API_KEY=\"\${OPENAI_API_KEY:-sk-local-dev-placeholder}\" .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload 2>&1 | tee /tmp/findraft-backend.log"
fi

if ! tmux has-session -t frontend 2>/dev/null; then
  tmux new-session -d -s frontend -c "$REPO_ROOT/frontend" -- bash -lc \
    'npm run dev -- --hostname 0.0.0.0 2>&1 | tee /tmp/findraft-frontend.log'
fi

for _ in $(seq 1 90); do
  if curl -sf http://127.0.0.1:8000/health >/dev/null \
    && curl -sf -o /dev/null http://127.0.0.1:43123/; then
    echo "PostgreSQL, backend, and frontend are ready."
    exit 0
  fi
  sleep 1
done

echo "Backend or frontend did not become ready" >&2
exit 1
