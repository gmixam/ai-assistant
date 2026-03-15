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
REDIS_CONTAINER="${REDIS_CONTAINER:-ai_redis}"
TASK_QUEUE_NAME="${TASK_QUEUE_NAME:-tasks:queue}"
COMPOSE_FILE="${COMPOSE_FILE:-infra/docker-compose.yml}"
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

resolve_container() {
  local requested="$1"
  local service="$2"
  if docker inspect "$requested" >/dev/null 2>&1; then
    printf '%s\n' "$requested"
    return 0
  fi
  local resolved
  resolved="$(docker compose -f "$COMPOSE_FILE" ps -q "$service" 2>/dev/null || true)"
  if [[ -n "$resolved" ]] && docker inspect "$resolved" >/dev/null 2>&1; then
    printf '%s\n' "$resolved"
    return 0
  fi
  return 1
}

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

BACKEND_CONTAINER="$(resolve_container "$BACKEND_CONTAINER" backend)" || fail "backend container not found: $BACKEND_CONTAINER"
WORKER_CONTAINER="$(resolve_container "$WORKER_CONTAINER" worker 2>/dev/null || true)"
docker inspect "$REDIS_CONTAINER" >/dev/null 2>&1 || fail "redis container not found: $REDIS_CONTAINER"

curl -fsS "$API_BASE_URL/health" >/dev/null || fail "backend healthcheck failed: $API_BASE_URL/health"
echo "PASS: backend healthcheck is reachable"

if [[ -n "$WORKER_CONTAINER" ]] && docker inspect "$WORKER_CONTAINER" >/dev/null 2>&1; then
  worker_running="$(
    docker inspect -f '{{.State.Running}}' "$WORKER_CONTAINER" 2>/dev/null || echo false
  )"
  [[ "$worker_running" != "true" ]] || fail "email team smoke requires ai_worker to be stopped: $WORKER_CONTAINER"
fi
echo "PASS: compose worker is not running"

existing_manual_worker_pids="$(list_backend_worker_runtime_pids)"
[[ -z "$existing_manual_worker_pids" ]] || fail "email team smoke requires no existing manual worker inside backend (found pids: $existing_manual_worker_pids)"
echo "PASS: no manual worker is running inside backend"

docker exec "$REDIS_CONTAINER" redis-cli DEL "$TASK_QUEUE_NAME" >/dev/null
echo "PASS: queue was reset for isolated email team smoke"

run_id="$(date -u +%Y%m%dT%H%M%SZ)"
mailbox="ops-team-$run_id@example.com"
contract_b64="$(printf 'Contract clause 1. Approval needed before reply.' | base64 -w0)"
sync_response="$(
  curl -fsS \
    -X POST "$API_BASE_URL/mailboxes/sync" \
    -H "Content-Type: application/json" \
    -d "{\"provider\":\"fake\",\"mailbox\":\"$mailbox\",\"provider_options\":{\"messages\":[{\"uid\":1001,\"provider_message_id\":\"fake-team-$run_id\",\"internet_message_id\":\"<team-$run_id@example.com>\",\"from_address\":\"legal@example.net\",\"subject\":\"Urgent contract review and approval\",\"snippet\":\"Please review the attached contract and approve the reply to the client by tomorrow.\",\"labels\":[\"INBOX\",\"IMPORTANT\"],\"telegram_chat_id\":10001,\"reply_to_message_id\":1,\"attachments\":[{\"attachment_id\":\"att-team-1\",\"filename\":\"contract.txt\",\"mime_type\":\"text/plain\",\"file_size\":52,\"is_inline\":false,\"content_base64\":\"$contract_b64\"}]}]}}"
)" || fail "POST /mailboxes/sync failed"

deep_count="$(
  printf '%s' "$sync_response" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("deep_count") or 0)'
)"
[[ "$deep_count" == "1" ]] || fail "mailbox sync deep_count expected 1, got: $deep_count"

email_lookup="$(
  docker exec -i "$BACKEND_CONTAINER" python3 - <<PY
from app.database import SessionLocal
from app.models import EmailSource

db = SessionLocal()
item = db.query(EmailSource).filter(EmailSource.provider_message_id == "fake-team-$run_id").first()
print(f"{item.id}|{item.task_id}|{item.routing_decision}" if item is not None else "||")
db.close()
PY
)"
IFS='|' read -r email_source_id task_id routing_decision <<<"$email_lookup"
[[ -n "$email_source_id" ]] || fail "email_source_id is missing"
[[ -n "$task_id" ]] || fail "deep email task_id is missing"
[[ "$routing_decision" == "deep" ]] || fail "routing_decision expected deep, got: $routing_decision"
echo "PASS: deep email intake created task"

worker_log_file="${TMPDIR:-/tmp}/smoke-email-team.$$.log"
worker_pid=""
cleanup() {
  if [[ -n "$worker_pid" ]] && kill -0 "$worker_pid" >/dev/null 2>&1; then
    kill "$worker_pid" >/dev/null 2>&1 || true
    wait "$worker_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

docker exec \
  -e TELEGRAM_DELIVERY_MODE=mock-success \
  -e MOCK_PROCESSING_DELAY_SECONDS=0 \
  "$BACKEND_CONTAINER" \
  python -m app.worker_runtime --max-tasks 1 >"$worker_log_file" 2>&1 &
worker_pid="$!"
sleep "$WORKER_STARTUP_SLEEP_SECONDS"

deadline=$((SECONDS + WORKER_WAIT_TIMEOUT_SECONDS))
last_status=""
while (( SECONDS < deadline )); do
  response="$(curl -fsS "$API_BASE_URL/tasks/$task_id")" || fail "GET /tasks/$task_id failed"
  last_status="$(
    printf '%s' "$response" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status") or "")'
  )"
  if [[ "$last_status" == "done" ]]; then
    break
  fi
  if [[ "$last_status" == "failed" ]]; then
    cat "$worker_log_file" || true
    fail "email team task reached failed"
  fi
  sleep "$WORKER_POLL_INTERVAL_SECONDS"
done
[[ "$last_status" == "done" ]] || fail "email team task did not reach done within timeout"
echo "PASS: email team task reached done"

approval_response="$(curl -fsS "$API_BASE_URL/tasks/$task_id/approvals")" || fail "GET /tasks/$task_id/approvals failed"
approval_count="$(
  printf '%s' "$approval_response" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("approvals") or []))'
)"
approval_status="$(
  printf '%s' "$approval_response" | python3 -c 'import json,sys; d=json.load(sys.stdin); approvals=d.get("approvals") or []; print((approvals[0].get("status") if approvals else ""))'
)"
approval_handoff="$(
  printf '%s' "$approval_response" | python3 -c 'import json,sys; d=json.load(sys.stdin); approvals=d.get("approvals") or []; print((approvals[0].get("handoff") if approvals else ""))'
)"
[[ "$approval_count" == "1" ]] || fail "expected one approval item, got: $approval_count"
[[ "$approval_status" == "pending" ]] || fail "approval status expected pending, got: $approval_status"
printf '%s' "$approval_handoff" | grep -q "await_human_approval" || fail "approval handoff missing await_human_approval"
echo "PASS: approval item created from email team flow"

email_response="$(curl -fsS "$API_BASE_URL/email-sources/$email_source_id")" || fail "GET /email-sources/$email_source_id failed"
returned_task_id="$(
  printf '%s' "$email_response" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("task_id") or "")'
)"
attachments_count="$(
  printf '%s' "$email_response" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("attachments_count") or 0)'
)"
[[ "$returned_task_id" == "$task_id" ]] || fail "email source task linkage mismatch"
[[ "$attachments_count" == "1" ]] || fail "email source attachments_count expected 1, got: $attachments_count"
echo "PASS: email source remains linked to deep task"

worker_logs="$(cat "$worker_log_file")"
printf '%s\n' "$worker_logs" | grep -q "event=agent_route_resolved task_id=$task_id task_type=email_triage agent_id=email_triage_agent team_id=email_triage_team" \
  || fail "email team route log not found"
printf '%s\n' "$worker_logs" | grep -q "event=team_step_started task_id=$task_id team_id=email_triage_team step_id=email_triage agent_id=email_triage_agent" \
  || fail "email_triage step start log not found"
printf '%s\n' "$worker_logs" | grep -q "event=agent_handoff task_id=$task_id team_id=email_triage_team from_agent_id=email_triage_agent to_agent_id=action_extraction_agent output_contract=email_triage_output next_input_contract=action_extraction_input" \
  || fail "triage handoff log not found"
printf '%s\n' "$worker_logs" | grep -q "event=attachment_analysis_reused task_id=$task_id team_id=email_triage_team agent_id=attachment_analysis_agent capability=document_analysis attachment_count=1" \
  || fail "attachment analysis reuse log not found"
printf '%s\n' "$worker_logs" | grep -q "event=mail_attachment_download_started provider=fake mailbox=$mailbox email_source_id=$email_source_id attachment_id=" \
  || fail "mail attachment download start log not found"
printf '%s\n' "$worker_logs" | grep -q "event=mail_attachment_download_completed provider=fake mailbox=$mailbox email_source_id=$email_source_id attachment_id=" \
  || fail "mail attachment download completion log not found"
printf '%s\n' "$worker_logs" | grep -q "event=approval_created task_id=$task_id approval_id=" \
  || fail "approval_created log not found"
printf '%s\n' "$worker_logs" | grep -q "event=approval_delivery_started task_id=$task_id approval_id=.* telegram_chat_id=10001 status=pending" \
  || fail "approval_delivery_started log not found"
printf '%s\n' "$worker_logs" | grep -q "event=approval_delivery_completed task_id=$task_id approval_id=.* telegram_chat_id=10001 status=pending" \
  || fail "approval_delivery_completed log not found"
printf '%s\n' "$worker_logs" | grep -q "event=task_finalized task_id=$task_id team_id=email_triage_team agent_id=approval_prep_agent final_status=done" \
  || fail "team finalization log not found"
echo "PASS: team flow structured logs are present"

echo "SMOKE EMAIL TEAM FLOW PASSED"
