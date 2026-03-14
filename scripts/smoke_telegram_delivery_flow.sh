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
WORKER_WAIT_TIMEOUT_SECONDS="${WORKER_WAIT_TIMEOUT_SECONDS:-40}"
WORKER_POLL_INTERVAL_SECONDS="${WORKER_POLL_INTERVAL_SECONDS:-1}"
FAKE_CHAT_ID="${FAKE_CHAT_ID:-123456789}"
FAKE_USER_ID="${FAKE_USER_ID:-987654321}"
FAKE_MESSAGE_ID="${FAKE_MESSAGE_ID:-1001}"

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
  docker exec -i "$BACKEND_CONTAINER" python3 - <<'PY'
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

if docker inspect "$WORKER_CONTAINER" >/dev/null 2>&1; then
  worker_running="$(
    docker inspect -f '{{.State.Running}}' "$WORKER_CONTAINER" 2>/dev/null || echo false
  )"
  [[ "$worker_running" != "true" ]] || fail "telegram delivery smoke requires ai_worker to be stopped: $WORKER_CONTAINER"
fi
echo "PASS: compose worker is not running"

manual_worker_pids="$(list_backend_worker_runtime_pids)"
[[ -z "$manual_worker_pids" ]] || fail "telegram delivery smoke requires no existing manual worker inside backend (found pids: $manual_worker_pids)"
echo "PASS: no manual worker is running inside backend"

worker_pid=""
cleanup() {
  if [[ -n "$worker_pid" ]] && kill -0 "$worker_pid" >/dev/null 2>&1; then
    kill "$worker_pid" >/dev/null 2>&1 || true
    wait "$worker_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

task_text="smoke-telegram-delivery-$(date -u +%Y%m%dT%H%M%SZ)"
post_response="$(
  curl -fsS \
    -X POST "$API_BASE_URL/tasks" \
    -H "Content-Type: application/json" \
    -d "{\"input_text\":\"$task_text\",\"telegram_chat_id\":$FAKE_CHAT_ID,\"telegram_user_id\":$FAKE_USER_ID,\"telegram_message_id\":$FAKE_MESSAGE_ID,\"reply_to_message_id\":$FAKE_MESSAGE_ID}"
)" || fail "POST /tasks failed"

task_id="$(
  printf '%s' "$post_response" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("task_id") or d.get("id") or "")'
)"
[[ -n "$task_id" ]] || fail "task_id is missing"
echo "PASS: delivery smoke task created"

# Force delivery failure while keeping worker processing path healthy in isolated debug mode.
docker exec \
  -e TASK_EXECUTOR=mock \
  -e TELEGRAM_API_BASE_URL=http://127.0.0.1:9 \
  -e TELEGRAM_DELIVERY_TIMEOUT_SECONDS=1 \
  "$BACKEND_CONTAINER" python -m app.worker_runtime >/tmp/smoke-telegram-delivery.$$.log 2>&1 &
worker_pid="$!"

deadline=$((SECONDS + WORKER_WAIT_TIMEOUT_SECONDS))
last_status=""
last_delivery_status=""
last_delivery_error=""
while (( SECONDS < deadline )); do
  response="$(curl -fsS "$API_BASE_URL/tasks/$task_id")" || fail "GET /tasks/{task_id} failed"
  last_status="$(
    printf '%s' "$response" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status") or "")'
  )"
  last_delivery_status="$(
    printf '%s' "$response" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("delivery_status") or "")'
  )"
  last_delivery_error="$(
    printf '%s' "$response" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("delivery_error") or "")'
  )"

  if [[ "$last_status" == "done" && "$last_delivery_status" == "failed" && -n "$last_delivery_error" ]]; then
    echo "PASS: delivery lifecycle reached failed without worker crash"
    echo "PASS: delivery_error is present"
    echo "SMOKE TELEGRAM DELIVERY PASSED"
    exit 0
  fi

  if [[ "$last_status" == "failed" ]]; then
    fail "task processing failed (expected done + delivery failed)"
  fi

  sleep "$WORKER_POLL_INTERVAL_SECONDS"
done

fail "delivery lifecycle did not reach expected state within timeout (status=$last_status delivery_status=$last_delivery_status)"
