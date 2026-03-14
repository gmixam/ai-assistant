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
REDIS_CONTAINER="${REDIS_CONTAINER:-ai_redis}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-ai_postgres}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-ai_backend}"
WORKER_CONTAINER="${WORKER_CONTAINER:-ai_worker}"
TASK_QUEUE_NAME="${TASK_QUEUE_NAME:-tasks:queue}"
POSTGRES_USER="${POSTGRES_USER:-ai_user}"
POSTGRES_DB="${POSTGRES_DB:-ai_assistant}"

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

docker inspect "$REDIS_CONTAINER" >/dev/null 2>&1 || fail "redis container not found: $REDIS_CONTAINER"
docker inspect "$POSTGRES_CONTAINER" >/dev/null 2>&1 || fail "postgres container not found: $POSTGRES_CONTAINER"
docker inspect "$BACKEND_CONTAINER" >/dev/null 2>&1 || fail "backend container not found: $BACKEND_CONTAINER"

curl -fsS "$API_BASE_URL/health" >/dev/null || fail "backend healthcheck failed: $API_BASE_URL/health"
echo "PASS: backend healthcheck is reachable"

if docker inspect "$WORKER_CONTAINER" >/dev/null 2>&1; then
  worker_running="$(
    docker inspect -f '{{.State.Running}}' "$WORKER_CONTAINER" 2>/dev/null || echo false
  )"
  [[ "$worker_running" != "true" ]] || fail "queue smoke requires ai_worker to be stopped: $WORKER_CONTAINER"
fi
echo "PASS: compose worker is not running"

manual_worker_pids="$(list_backend_worker_runtime_pids)"
[[ -z "$manual_worker_pids" ]] || fail "queue smoke requires no manual worker inside backend (found pids: $manual_worker_pids)"
echo "PASS: no manual worker is running inside backend"

task_text="smoke-task-$(date -u +%Y%m%dT%H%M%SZ)"

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
echo "PASS: task created"

get_response="$(curl -fsS "$API_BASE_URL/tasks/$task_id")" || fail "GET /tasks/{task_id} failed"

returned_id="$(
  printf '%s' "$get_response" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id") or "")'
)"
[[ "$returned_id" == "$task_id" ]] || fail "task returned by API does not match created task_id"
echo "PASS: task returned by API"

task_status="$(
  printf '%s' "$get_response" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status") or "")'
)"
if [[ "$task_status" != "queued" ]]; then
  if [[ "$task_status" == "processing" || "$task_status" == "done" || "$task_status" == "failed" ]]; then
    fail "task left queued state unexpectedly ($task_status); isolated queue smoke detected worker competition"
  fi
  fail "task status expected queued, got: $task_status"
fi
echo "PASS: task status is queued"

docker exec "$REDIS_CONTAINER" redis-cli --raw LRANGE "$TASK_QUEUE_NAME" 0 -1 \
  | grep -Fxq "$task_id" \
  || fail "task_id not found in Redis queue $TASK_QUEUE_NAME"
echo "PASS: task found in Redis queue"

docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
  "SELECT 1 FROM tasks WHERE id = '$task_id' LIMIT 1;" \
  | grep -qx "1" \
  || fail "task_id not found in PostgreSQL tasks table"
echo "PASS: task found in PostgreSQL"

echo "SMOKE TEST PASSED"
