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

docker inspect "$BACKEND_CONTAINER" >/dev/null 2>&1 || fail "backend container not found: $BACKEND_CONTAINER"

worker_log_file="${TMPDIR:-/tmp}/smoke-worker.$$.log"
worker_pid=""
worker_runtime_pid=""

list_worker_runtime_pids() {
  python3 - <<'PY'
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

cleanup() {
  if [[ -n "$worker_pid" ]] && kill -0 "$worker_pid" >/dev/null 2>&1; then
    kill "$worker_pid" >/dev/null 2>&1 || true
    wait "$worker_pid" 2>/dev/null || true
  fi
  if [[ -n "$worker_runtime_pid" ]] && kill -0 "$worker_runtime_pid" >/dev/null 2>&1; then
    kill "$worker_runtime_pid" >/dev/null 2>&1 || true
    wait "$worker_runtime_pid" 2>/dev/null || true
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

before_worker_pids="$(list_worker_runtime_pids)"
if [[ -n "$TASK_EXECUTOR" ]]; then
  docker exec -e TASK_EXECUTOR="$TASK_EXECUTOR" "$BACKEND_CONTAINER" python -m app.worker_runtime >"$worker_log_file" 2>&1 &
else
  docker exec "$BACKEND_CONTAINER" python -m app.worker_runtime >"$worker_log_file" 2>&1 &
fi
worker_pid="$!"
sleep "$WORKER_STARTUP_SLEEP_SECONDS"
worker_runtime_pid="$(
  BEFORE_WORKER_PIDS="$before_worker_pids" python3 - <<'PY'
import os

before = {pid for pid in os.getenv("BEFORE_WORKER_PIDS", "").splitlines() if pid.strip()}
current = []
for pid in sorted(os.listdir("/proc"), key=lambda x: int(x) if x.isdigit() else 10**9):
    if not pid.isdigit():
        continue
    try:
        cmdline = open(f"/proc/{pid}/cmdline", "rb").read().decode("utf-8", "ignore").replace("\x00", " ").strip()
    except Exception:
        continue
    if "python -m app.worker_runtime" in cmdline and pid not in before:
        current.append(pid)
print(current[-1] if current else "")
PY
)"

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
    cat "$worker_log_file" || true
    fail "worker lifecycle reached failed"
  fi

  sleep "$WORKER_POLL_INTERVAL_SECONDS"
done

echo "Worker logs:"
cat "$worker_log_file" || true
fail "worker did not reach ${EXPECTED_FINAL_STATUS} within ${WORKER_WAIT_TIMEOUT_SECONDS}s (last status: ${last_status:-unknown})"
