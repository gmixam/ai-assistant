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
WORKER_CONTAINER="${WORKER_CONTAINER:-ai_worker}"
WORKER_MODE="${WORKER_MODE:-service}"
WORKER_WAIT_TIMEOUT_SECONDS="${WORKER_WAIT_TIMEOUT_SECONDS:-40}"
WORKER_POLL_INTERVAL_SECONDS="${WORKER_POLL_INTERVAL_SECONDS:-1}"
WORKER_STARTUP_SLEEP_SECONDS="${WORKER_STARTUP_SLEEP_SECONDS:-1}"
EXPECTED_FINAL_STATUS="${EXPECTED_FINAL_STATUS:-done}"
TASK_EXECUTOR="${TASK_EXECUTOR:-}"

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

list_backend_worker_runtime_pids() {
  docker exec "$BACKEND_CONTAINER" python3 - <<'PY'
import os

for pid in sorted(os.listdir("/proc"), key=lambda x: int(x) if x.isdigit() else 10**9):
    if not pid.isdigit():
        continue
    try:
        cmdline = open(f"/proc/{pid}/cmdline", "rb").read().decode("utf-8", "ignore").replace("\x00", " ").strip()
    except Exception:
        continue
    if "python -m app.worker_runtime" in cmdline:
        print(pid)
PY
}

docker inspect "$BACKEND_CONTAINER" >/dev/null 2>&1 || fail "backend container not found: $BACKEND_CONTAINER"
curl -fsS "$API_BASE_URL/health" >/dev/null || fail "backend healthcheck failed: $API_BASE_URL/health"
echo "PASS: backend healthcheck is reachable"

if [[ -n "$TASK_EXECUTOR" && "$WORKER_MODE" == "service" ]]; then
  WORKER_MODE="debug"
fi

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

if [[ "$WORKER_MODE" == "service" ]]; then
  docker inspect "$WORKER_CONTAINER" >/dev/null 2>&1 || fail "worker container not found: $WORKER_CONTAINER"
  worker_running="$(
    docker inspect -f '{{.State.Running}}' "$WORKER_CONTAINER" 2>/dev/null || echo false
  )"
  [[ "$worker_running" == "true" ]] || fail "worker container is not running: $WORKER_CONTAINER"
  echo "PASS: compose worker is running"
  manual_worker_pids="$(list_backend_worker_runtime_pids)"
  [[ -z "$manual_worker_pids" ]] || fail "service smoke requires no manual worker inside backend (found pids: $manual_worker_pids)"
  echo "PASS: no manual worker is running inside backend"
else
  if docker inspect "$WORKER_CONTAINER" >/dev/null 2>&1; then
    worker_running="$(
      docker inspect -f '{{.State.Running}}' "$WORKER_CONTAINER" 2>/dev/null || echo false
    )"
    [[ "$worker_running" != "true" ]] || fail "debug smoke requires ai_worker to be stopped: $WORKER_CONTAINER"
  fi
  existing_manual_worker_pids="$(list_backend_worker_runtime_pids)"
  [[ -z "$existing_manual_worker_pids" ]] || fail "debug smoke requires no existing manual worker inside backend (found pids: $existing_manual_worker_pids)"
  echo "PASS: smoke debug mode is isolated from normal worker runtime"
  if [[ -n "$TASK_EXECUTOR" ]]; then
    docker exec -e TASK_EXECUTOR="$TASK_EXECUTOR" "$BACKEND_CONTAINER" python -m app.worker_runtime >"$worker_log_file" 2>&1 &
  else
    docker exec "$BACKEND_CONTAINER" python -m app.worker_runtime >"$worker_log_file" 2>&1 &
  fi
  worker_pid="$!"
  sleep "$WORKER_STARTUP_SLEEP_SECONDS"
fi

deadline=$((SECONDS + WORKER_WAIT_TIMEOUT_SECONDS))
last_status=""
last_result_text=""
last_error_text=""

while (( SECONDS < deadline )); do
  response="$(curl -fsS "$API_BASE_URL/tasks/$task_id")" || fail "GET /tasks/{task_id} failed"
  last_status="$(
    printf '%s' "$response" \
      | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status") or "")'
  )"
  last_result_text="$(
    printf '%s' "$response" \
      | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("result_text") or "")'
  )"
  last_error_text="$(
    printf '%s' "$response" \
      | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("error_text") or "")'
  )"

  if [[ "$last_status" == "$EXPECTED_FINAL_STATUS" ]]; then
    if [[ "$EXPECTED_FINAL_STATUS" == "done" ]]; then
      [[ -n "$last_result_text" ]] || fail "task reached done but result_text is empty"
      echo "PASS: worker lifecycle reached done"
      echo "PASS: worker result_text is present"
    elif [[ "$EXPECTED_FINAL_STATUS" == "failed" ]]; then
      [[ -n "$last_error_text" ]] || fail "task reached failed but error_text is empty"
      echo "PASS: worker lifecycle reached failed"
      echo "PASS: worker error_text is present"
    fi
    echo "SMOKE WORKER TEST PASSED"
    exit 0
  fi

  if [[ "$last_status" == "failed" ]]; then
    if [[ "$EXPECTED_FINAL_STATUS" == "failed" ]]; then
      continue
    fi
    echo "Worker logs:"
    if [[ "$WORKER_MODE" == "service" ]]; then
      docker logs --tail=50 "$WORKER_CONTAINER" || true
    else
      cat "$worker_log_file" || true
    fi
    fail "worker lifecycle reached failed"
  fi

  sleep "$WORKER_POLL_INTERVAL_SECONDS"
done

echo "Worker logs:"
if [[ "$WORKER_MODE" == "service" ]]; then
  docker logs --tail=50 "$WORKER_CONTAINER" || true
else
  cat "$worker_log_file" || true
fi
fail "worker did not reach ${EXPECTED_FINAL_STATUS} within ${WORKER_WAIT_TIMEOUT_SECONDS}s (last status: ${last_status:-unknown})"
