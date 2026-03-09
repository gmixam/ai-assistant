#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +a
fi

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-ai_backend}"
WORKER_WAIT_TIMEOUT_SECONDS="${WORKER_WAIT_TIMEOUT_SECONDS:-40}"
WORKER_POLL_INTERVAL_SECONDS="${WORKER_POLL_INTERVAL_SECONDS:-1}"
WORKER_STARTUP_SLEEP_SECONDS="${WORKER_STARTUP_SLEEP_SECONDS:-1}"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

require_cmd curl
require_cmd docker
require_cmd python3

docker inspect "$BACKEND_CONTAINER" >/dev/null 2>&1 || fail "backend container not found: $BACKEND_CONTAINER"

worker_log_file="${TMPDIR:-/tmp}/smoke-worker.$$.log"
worker_pid=""

cleanup() {
  if [[ -n "$worker_pid" ]] && kill -0 "$worker_pid" >/dev/null 2>&1; then
    kill "$worker_pid" >/dev/null 2>&1 || true
    wait "$worker_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

task_text="smoke-worker-$(date -u +%Y%m%dT%H%M%SZ)"
post_response="$(
  curl -fsS \
    -X POST "$API_BASE_URL/tasks" \
    -H "Content-Type: application/json" \
    -d "{\"input_text\":\"$task_text\"}"
)" || fail "POST /tasks failed"

task_id="$(
  printf '%s' "$post_response" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("task_id") or d.get("id") or "")'
)"
[[ -n "$task_id" ]] || fail "task_id is missing in POST /tasks response"
echo "PASS: worker smoke task created"

docker exec "$BACKEND_CONTAINER" python -m app.worker_runtime >"$worker_log_file" 2>&1 &
worker_pid="$!"
sleep "$WORKER_STARTUP_SLEEP_SECONDS"

deadline=$((SECONDS + WORKER_WAIT_TIMEOUT_SECONDS))
last_status=""

while (( SECONDS < deadline )); do
  response="$(curl -fsS "$API_BASE_URL/tasks/$task_id")" || fail "GET /tasks/{task_id} failed"
  last_status="$(
    printf '%s' "$response" \
      | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status") or "")'
  )"

  if [[ "$last_status" == "done" ]]; then
    echo "PASS: worker lifecycle reached done"
    echo "SMOKE WORKER TEST PASSED"
    exit 0
  fi

  if [[ "$last_status" == "failed" ]]; then
    echo "Worker logs:"
    cat "$worker_log_file" || true
    fail "worker lifecycle reached failed"
  fi

  sleep "$WORKER_POLL_INTERVAL_SECONDS"
done

echo "Worker logs:"
cat "$worker_log_file" || true
fail "worker did not reach done within ${WORKER_WAIT_TIMEOUT_SECONDS}s (last status: ${last_status:-unknown})"
