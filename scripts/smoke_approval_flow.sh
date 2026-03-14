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
BOT_CONTAINER="${BOT_CONTAINER:-ai_bot}"
COMPOSE_FILE="${COMPOSE_FILE:-infra/docker-compose.yml}"
BACKEND_WAIT_TIMEOUT_SECONDS="${BACKEND_WAIT_TIMEOUT_SECONDS:-30}"

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

BACKEND_CONTAINER="$(resolve_container "$BACKEND_CONTAINER" backend)" || fail "backend container not found: $BACKEND_CONTAINER"
BOT_CONTAINER="$(resolve_container "$BOT_CONTAINER" bot)" || fail "bot container not found: $BOT_CONTAINER"

backend_deadline=$((SECONDS + BACKEND_WAIT_TIMEOUT_SECONDS))
until curl -fsS "$API_BASE_URL/health" >/dev/null 2>&1; do
  (( SECONDS < backend_deadline )) || fail "backend healthcheck failed: $API_BASE_URL/health"
  sleep 1
done
echo "PASS: backend healthcheck is reachable"

task_text="smoke-approval-$(date -u +%Y%m%dT%H%M%SZ)"
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
echo "PASS: approval smoke task created"

approval_response="$(
  curl -fsS \
    -X POST "$API_BASE_URL/tasks/$task_id/approvals" \
    -H "Content-Type: application/json" \
    -d '{"summary":"Review outbound response draft","proposed_action":"send_client_reply","structured_result":{"result_type":"approval_request","action_type":"send_client_reply"},"handoff":"await_human_approval"}'
)" || fail "POST /tasks/{id}/approvals failed"

approval_id="$(
  printf '%s' "$approval_response" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id") or "")'
)"
approval_status="$(
  printf '%s' "$approval_response" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status") or "")'
)"
[[ -n "$approval_id" ]] || fail "approval_id is missing"
[[ "$approval_status" == "pending" ]] || fail "approval status expected pending, got: $approval_status"
echo "PASS: approval item creation works"

summary_render="$(
  docker exec "$BACKEND_CONTAINER" python -c 'from app.models import ApprovalItem; from app.telegram_delivery import build_approval_message; item = ApprovalItem(id=1, task_id="'"$task_id"'", status="pending", summary="Review outbound response draft", proposed_action="send_client_reply", structured_result="{\"result_type\":\"approval_request\",\"action_type\":\"send_client_reply\"}", handoff="await_human_approval"); print(build_approval_message(item))'
)"
printf '%s\n' "$summary_render" | grep -q "Status: pending approval" || fail "approval summary missing pending approval status"
printf '%s\n' "$summary_render" | grep -q "Action type: send_client_reply" || fail "approval summary missing action type"
printf '%s\n' "$summary_render" | grep -q "Suggested next step: Review details on demand, then approve or reject." || fail "approval summary missing next step"

details_render="$(
  docker exec "$BOT_CONTAINER" python -c 'from app.main import _format_approval_details; print(_format_approval_details({"id": 1, "task_id": "'"$task_id"'", "status": "pending", "summary": "Review outbound response draft", "proposed_action": "send_client_reply", "structured_result": "{\"result_type\":\"approval_request\",\"action_type\":\"send_client_reply\"}", "handoff": "await_human_approval"}))'
)"
printf '%s\n' "$details_render" | grep -q "Details:" || fail "approval details view missing details block"
printf '%s\n' "$details_render" | grep -q "Handoff: await_human_approval" || fail "approval details view missing handoff"
echo "PASS: Telegram rendering path is correct"

delivery_log_marker="approval-smoke-$approval_id"
delivery_output="$(
docker exec -i -e APPROVAL_ID="$approval_id" -e TASK_ID="$task_id" -e DELIVERY_LOG_MARKER="$delivery_log_marker" "$BACKEND_CONTAINER" python - <<'PY'
import io
import json
import logging
import os
import sys
from unittest.mock import patch

from app.models import ApprovalItem, Task
from app.telegram_delivery import deliver_approval_to_telegram, logger

task = Task(id=os.environ["TASK_ID"], telegram_chat_id=10001, reply_to_message_id=1)
item = ApprovalItem(
    id=int(os.environ["APPROVAL_ID"]),
    task_id=os.environ["TASK_ID"],
    status="pending",
    summary="Review outbound response draft",
    proposed_action="send_client_reply",
    structured_result='{"result_type":"approval_request","action_type":"send_client_reply"}',
    handoff="await_human_approval",
)

class FakeResponse:
    def __enter__(self):
        self._payload = io.BytesIO(json.dumps({"ok": True, "result": {"message_id": 42}}).encode("utf-8"))
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._payload.read()

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
logger.handlers = [handler]
logger.setLevel(logging.INFO)
logger.propagate = False
with patch("app.telegram_delivery.urllib.request.urlopen", return_value=FakeResponse()):
    logger.info("event=approval_smoke_delivery_invoked task_id=%s approval_id=%s marker=%s", task.id, item.id, os.environ["DELIVERY_LOG_MARKER"])
    outcome = deliver_approval_to_telegram(task, item)
    if not outcome.success:
        raise SystemExit("delivery helper reported failure")
PY
 2>&1)"

backend_logs="$(docker compose -f infra/docker-compose.yml logs --tail=300 backend)"
printf '%s\n' "$backend_logs" | grep -q "event=approval_created task_id=$task_id approval_id=$approval_id status=pending" \
  || fail "approval_created log not found"
printf '%s\n' "$delivery_output" | grep -q "event=approval_delivery_started task_id=$task_id approval_id=$approval_id telegram_chat_id=10001 status=pending" \
  || fail "approval_delivery_started log not found"
printf '%s\n' "$delivery_output" | grep -q "event=approval_delivery_completed task_id=$task_id approval_id=$approval_id telegram_chat_id=10001 status=pending" \
  || fail "approval_delivery_completed log not found"
echo "PASS: approval delivery lifecycle logs are present"

approve_response="$(
  curl -fsS \
    -X POST "$API_BASE_URL/approvals/$approval_id/approve" \
    -H "Content-Type: application/json" \
    -d '{"decided_by":"smoke-user"}'
)" || fail "POST /approvals/{id}/approve failed"
approve_status="$(
  printf '%s' "$approve_response" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status") or "")'
)"
[[ "$approve_status" == "approved" ]] || fail "approve transition expected approved, got: $approve_status"
echo "PASS: approve transition works"

approve_repeat_response="$(
  curl -fsS \
    -X POST "$API_BASE_URL/approvals/$approval_id/approve" \
    -H "Content-Type: application/json" \
    -d '{"decided_by":"smoke-user-repeat"}'
)" || fail "repeat approve failed"
approve_repeat_status="$(
  printf '%s' "$approve_repeat_response" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status") or "")'
)"
[[ "$approve_repeat_status" == "approved" ]] || fail "repeat approve changed status unexpectedly: $approve_repeat_status"

reject_after_approve_response="$(
  curl -fsS \
    -X POST "$API_BASE_URL/approvals/$approval_id/reject" \
    -H "Content-Type: application/json" \
    -d '{"decided_by":"smoke-user-conflict"}'
)" || fail "reject after approve failed"
reject_after_approve_status="$(
  printf '%s' "$reject_after_approve_response" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status") or "")'
)"
[[ "$reject_after_approve_status" == "approved" ]] || fail "approval item was processed twice unexpectedly: $reject_after_approve_status"
echo "PASS: approve idempotency is safe"

reject_item_response="$(
  curl -fsS \
    -X POST "$API_BASE_URL/tasks/$task_id/approvals" \
    -H "Content-Type: application/json" \
    -d '{"summary":"Reject-only regression path","proposed_action":"hold_reply","structured_result":{"result_type":"approval_request","action_type":"hold_reply"},"handoff":"await_human_approval"}'
)" || fail "second approval creation failed"
reject_approval_id="$(
  printf '%s' "$reject_item_response" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id") or "")'
)"
[[ -n "$reject_approval_id" ]] || fail "second approval id is missing"

reject_response="$(
  curl -fsS \
    -X POST "$API_BASE_URL/approvals/$reject_approval_id/reject" \
    -H "Content-Type: application/json" \
    -d '{"decided_by":"smoke-user"}'
)" || fail "POST /approvals/{id}/reject failed"
reject_status="$(
  printf '%s' "$reject_response" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status") or "")'
)"
[[ "$reject_status" == "rejected" ]] || fail "reject transition expected rejected, got: $reject_status"

reject_repeat_response="$(
  curl -fsS \
    -X POST "$API_BASE_URL/approvals/$reject_approval_id/reject" \
    -H "Content-Type: application/json" \
    -d '{"decided_by":"smoke-user-repeat"}'
)" || fail "repeat reject failed"
reject_repeat_status="$(
  printf '%s' "$reject_repeat_response" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status") or "")'
)"
[[ "$reject_repeat_status" == "rejected" ]] || fail "repeat reject changed status unexpectedly: $reject_repeat_status"

approve_after_reject_response="$(
  curl -fsS \
    -X POST "$API_BASE_URL/approvals/$reject_approval_id/approve" \
    -H "Content-Type: application/json" \
    -d '{"decided_by":"smoke-user-conflict"}'
)" || fail "approve after reject failed"
approve_after_reject_status="$(
  printf '%s' "$approve_after_reject_response" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status") or "")'
)"
[[ "$approve_after_reject_status" == "rejected" ]] || fail "rejected approval item was processed twice unexpectedly: $approve_after_reject_status"
echo "PASS: reject idempotency is safe"

expired_response="$(
  curl -fsS \
    -X POST "$API_BASE_URL/tasks/$task_id/approvals" \
    -H "Content-Type: application/json" \
    -d "{\"summary\":\"Expired approval regression path\",\"proposed_action\":\"do_nothing\",\"expires_at\":\"2000-01-01T00:00:00Z\"}"
)" || fail "expired approval creation failed"
expired_approval_id="$(
  printf '%s' "$expired_response" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id") or "")'
)"
expired_read_response="$(curl -fsS "$API_BASE_URL/approvals/$expired_approval_id")" || fail "GET /approvals/{id} failed for expired approval"
expired_status="$(
  printf '%s' "$expired_read_response" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status") or "")'
)"
[[ "$expired_status" == "expired" ]] || fail "expired approval expected expired, got: $expired_status"
echo "PASS: expired approval state is readable"

backend_logs="$(docker compose -f infra/docker-compose.yml logs --tail=400 backend)"
printf '%s\n' "$backend_logs" | grep -q "event=approval_approved task_id=$task_id approval_id=$approval_id status=approved idempotent=false" \
  || fail "approval_approved transition log not found"
printf '%s\n' "$backend_logs" | grep -q "event=approval_approved task_id=$task_id approval_id=$approval_id status=approved idempotent=true" \
  || fail "approval_approved idempotent log not found"
printf '%s\n' "$backend_logs" | grep -q "event=approval_rejected task_id=$task_id approval_id=$reject_approval_id status=rejected idempotent=false" \
  || fail "approval_rejected transition log not found"
printf '%s\n' "$backend_logs" | grep -q "event=approval_rejected task_id=$task_id approval_id=$reject_approval_id status=rejected idempotent=true" \
  || fail "approval_rejected idempotent log not found"
echo "PASS: approval transition logs are present"

task_approvals_response="$(curl -fsS "$API_BASE_URL/tasks/$task_id/approvals")" || fail "GET /tasks/{id}/approvals failed"
task_approvals_count="$(
  printf '%s' "$task_approvals_response" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("approvals") or []))'
)"
[[ "$task_approvals_count" -ge 3 ]] || fail "task approvals list did not include created approval items"
echo "PASS: approval status can be read through task API"

echo "SMOKE APPROVAL FLOW PASSED"
