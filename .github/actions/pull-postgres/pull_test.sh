#!/usr/bin/env bash
# Retry, login, and cache behaviour of pull.sh, with a stand-in for docker.
set -euo pipefail

root="$(cd "$(dirname "$0")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

cat > "$work/docker" << 'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$DOCKER_LOG"
case "$1" in
  login)
    if [[ "${DOCKER_LOGIN_FAIL:-}" == "1" ]]; then
      exit 1
    fi
    exit 0
    ;;
  pull)
    image="$2"
    count_file="$DOCKER_LOG.${image//\//_}.count"
    count=0
    if [[ -f "$count_file" ]]; then
      count="$(cat "$count_file")"
    fi
    count=$((count + 1))
    printf '%s' "$count" > "$count_file"
    fail_until="${DOCKER_FAIL_UNTIL:-0}"
    if [[ "$image" == "${DOCKER_FAIL_IMAGE:-}" && "$count" -le "$fail_until" ]]; then
      exit 1
    fi
    if [[ "$image" == "${DOCKER_ALWAYS_FAIL_IMAGE:-}" ]]; then
      exit 1
    fi
    exit 0
    ;;
  tag|run|exec)
    exit 0
    ;;
  save)
    printf 'image\n' 
    exit 0
    ;;
  load)
    exit 0
    ;;
  *)
    echo "unexpected docker $*" >&2
    exit 1
    ;;
esac
EOF
chmod +x "$work/docker"

run_pull() {
  DOCKER_LOG="$work/docker.log" \
    PATH="$work:$PATH" \
    CACHE_TAR="$work/postgres-15.tar.gz" \
    PULL_ATTEMPTS=4 \
    BACKOFF_SECONDS="0 0 0" \
    START=false \
    bash "$root/pull.sh"
}

assert_log() {
  local pattern="$1"
  if ! grep -F -- "$pattern" "$work/docker.log" >/dev/null; then
    echo "missing log line: $pattern" >&2
    cat "$work/docker.log" >&2
    exit 1
  fi
}

# Authenticated pull retries twice, then succeeds. Anonymous registries stay unused.
: > "$work/docker.log"
DOCKER_FAIL_IMAGE="postgres:15" DOCKER_FAIL_UNTIL=2 \
  DOCKERHUB_USERNAME=ci-reader DOCKERHUB_TOKEN=read-only-token \
  run_pull > "$work/out.txt"
assert_log "login docker.io --username ci-reader --password-stdin"
assert_log "pull postgres:15"
test "$(grep -c 'pull postgres:15' "$work/docker.log")" -eq 3
if grep -F 'public.ecr.aws' "$work/docker.log" >/dev/null; then
  echo "authenticated success still pulled the anonymous mirror" >&2
  exit 1
fi
gzip -t "$work/postgres-15.tar.gz"
if ! grep -F 'attempt 3' "$work/out.txt" >/dev/null; then
  echo "retry did not record the successful attempt" >&2
  cat "$work/out.txt" >&2
  exit 1
fi

# No credentials: anonymous ECR pull, no login.
rm -f "$work/postgres-15.tar.gz" "$work"/docker.log.*
: > "$work/docker.log"
unset DOCKERHUB_USERNAME DOCKERHUB_TOKEN
run_pull > "$work/out.txt"
if grep -F 'login ' "$work/docker.log" >/dev/null; then
  echo "anonymous run logged in" >&2
  exit 1
fi
assert_log "pull public.ecr.aws/docker/library/postgres:15"
if ! grep -F 'credentials are absent' "$work/out.txt" >/dev/null; then
  echo "missing absent-credentials note" >&2
  exit 1
fi

# Cache hit loads the tarball and does not pull.
printf 'image\n' | gzip -c > "$work/postgres-15.tar.gz"
: > "$work/docker.log"
unset DOCKERHUB_USERNAME DOCKERHUB_TOKEN
CACHE_HIT=true run_pull > "$work/out.txt"
assert_log "load"
if grep -E '^(pull|login) ' "$work/docker.log" >/dev/null; then
  echo "cache hit still contacted a registry" >&2
  cat "$work/docker.log" >&2
  exit 1
fi

# ECR failures fall through to an anonymous Docker Hub pull.
rm -f "$work/postgres-15.tar.gz" "$work"/docker.log.*
: > "$work/docker.log"
unset DOCKERHUB_USERNAME DOCKERHUB_TOKEN
DOCKER_ALWAYS_FAIL_IMAGE="public.ecr.aws/docker/library/postgres:15" \
  run_pull > "$work/out.txt"
test "$(grep -c 'pull public.ecr.aws/docker/library/postgres:15' "$work/docker.log")" -eq 4
assert_log "pull postgres:15"

echo "pull-postgres retry tests passed"
