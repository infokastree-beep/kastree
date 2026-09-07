#!/usr/bin/env bash
# Cloud Agent start script for FinDraft (Kastree).
#
# Runs on every boot before the terminals launch. Brings up the PostgreSQL
# service (its process does not survive across boots even when the data dir is
# snapshotted) and waits until it accepts connections. Schema/data setup lives
# in install.sh, never here.
set -euo pipefail

PG_VER="$(ls /usr/lib/postgresql/ 2>/dev/null | sort -n | tail -1)"
if [ -n "${PG_VER:-}" ]; then
  sudo pg_ctlcluster "$PG_VER" main start 2>/dev/null || true
  for _ in $(seq 1 30); do
    if sudo -u postgres pg_isready -q; then break; fi
    sleep 1
  done
fi

echo "PostgreSQL is ready."
