#!/usr/bin/env bash
# Pull postgres:15 once, or load a tarball restored from the Actions cache.
#
# Authenticated pulls use Docker Hub (docker.io), image library/postgres:15.
# DOCKERHUB_TOKEN must be a Personal Access Token with the Public Repo
# Read-only scope. An ECR Public authorization token is not stored: it
# expires after 12 hours.
#
# Fork pull requests do not receive repository secrets, and their Actions
# cache is isolated from this repository. Those runs skip login and pull
# anonymously, with the same retry. A same-repository run with the secrets
# unset does the same.
set -euo pipefail

CACHE_TAR="${CACHE_TAR:-/tmp/postgres-15.tar.gz}"
LOCAL_TAG="${LOCAL_TAG:-postgres:15}"
PULL_ATTEMPTS="${PULL_ATTEMPTS:-4}"
BACKOFF_SECONDS="${BACKOFF_SECONDS:-10 20 40}"
START="${START:-false}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-local}"
POSTGRES_DB="${POSTGRES_DB:-findraft_ci}"

write_output() {
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    printf '%s\n' "$1" >> "$GITHUB_OUTPUT"
  fi
}

note() {
  printf '%s\n' "$1"
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    printf '%s\n' "$1" >> "$GITHUB_STEP_SUMMARY"
  fi
}

pull_with_retry() {
  local image="$1"
  local attempt=1
  local -a waits
  local wait_seconds
  IFS=' ' read -r -a waits <<< "$BACKOFF_SECONDS"
  while true; do
    if docker pull "$image"; then
      note "Pulled ${image} on attempt ${attempt}."
      return 0
    fi
    if (( attempt >= PULL_ATTEMPTS )); then
      note "Stopped pulling ${image} after ${attempt} attempts."
      return 1
    fi
    wait_seconds="${waits[attempt - 1]:-40}"
    note "Pull attempt ${attempt} of ${image} failed. Waiting ${wait_seconds}s."
    sleep "$wait_seconds"
    attempt=$((attempt + 1))
  done
}

start_server() {
  docker run -d --name ci-postgres \
    -e "POSTGRES_USER=${POSTGRES_USER}" \
    -e "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" \
    -e "POSTGRES_DB=${POSTGRES_DB}" \
    -p 5432:5432 \
    "$LOCAL_TAG"
  local _try
  for _try in $(seq 1 30); do
    if docker exec ci-postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"; then
      note "Postgres is accepting connections."
      return 0
    fi
    sleep 2
  done
  docker logs ci-postgres || true
  note "Postgres did not become ready."
  return 1
}

source_label=""
pulled="false"

if [[ "${CACHE_HIT:-}" == "true" && -f "$CACHE_TAR" ]]; then
  gzip -dc "$CACHE_TAR" | docker load
  source_label="actions cache"
  note "Loaded ${LOCAL_TAG} from the Actions cache."
else
  if [[ -n "${DOCKERHUB_USERNAME:-}" && -n "${DOCKERHUB_TOKEN:-}" ]]; then
    if printf '%s' "$DOCKERHUB_TOKEN" | docker login docker.io --username "$DOCKERHUB_USERNAME" --password-stdin; then
      note "Logged in to docker.io."
      if pull_with_retry "$LOCAL_TAG"; then
        source_label="docker.io/library/postgres:15 (authenticated)"
      else
        note "Authenticated Docker Hub pull failed. Trying an anonymous pull."
      fi
    else
      note "Docker Hub login failed. Trying an anonymous pull."
    fi
  else
    note "Docker Hub credentials are absent. Fork pull requests do not receive repository secrets. Anonymous pull with retry."
  fi

  if [[ -z "$source_label" ]]; then
    ecr_image="public.ecr.aws/docker/library/postgres:15"
    if pull_with_retry "$ecr_image"; then
      docker tag "$ecr_image" "$LOCAL_TAG"
      source_label="${ecr_image} (anonymous)"
    elif pull_with_retry "$LOCAL_TAG"; then
      source_label="docker.io/library/postgres:15 (anonymous)"
    else
      note "Postgres image pull failed."
      exit 1
    fi
  fi

  mkdir -p "$(dirname "$CACHE_TAR")"
  docker save "$LOCAL_TAG" | gzip -c > "$CACHE_TAR"
  pulled="true"
  note "Saved ${LOCAL_TAG} for the Actions cache."
fi

write_output "pulled=${pulled}"
write_output "source=${source_label}"

if [[ "$START" == "true" ]]; then
  start_server
fi
