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
COMPOSE_FILE="${COMPOSE_FILE:-infra/docker-compose.yml}"
WORKER_WAIT_TIMEOUT_SECONDS="${WORKER_WAIT_TIMEOUT_SECONDS:-40}"
WORKER_POLL_INTERVAL_SECONDS="${WORKER_POLL_INTERVAL_SECONDS:-1}"
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
WORKER_CONTAINER="$(resolve_container "$WORKER_CONTAINER" worker)" || fail "worker container not found: $WORKER_CONTAINER"

backend_deadline=$((SECONDS + BACKEND_WAIT_TIMEOUT_SECONDS))
until curl -fsS "$API_BASE_URL/health" >/dev/null 2>&1; do
  (( SECONDS < backend_deadline )) || fail "backend healthcheck failed: $API_BASE_URL/health"
  sleep 1
done
echo "PASS: backend healthcheck is reachable"

worker_running="$(
  docker inspect -f '{{.State.Running}}' "$WORKER_CONTAINER" 2>/dev/null || echo false
)"
[[ "$worker_running" == "true" ]] || fail "worker container is not running: $WORKER_CONTAINER"
echo "PASS: compose worker is running"

registry_check="$(
python3 - <<'PY'
from backend.app.agents.registry import FileAgentRegistry

registry = FileAgentRegistry()
team = registry.get_team("email_triage_team")
document_agent = registry.get_agent("document_analysis_agent")
entrypoint = registry.resolve_entrypoint("document_analysis")
steps = ",".join(step.step_id for step in team.workflow_steps)
print("|".join([entrypoint, document_agent.team_id or "", team.team_id, steps]))
PY
)"
IFS='|' read -r entrypoint document_team team_id steps <<<"$registry_check"
[[ "$entrypoint" == "document_analysis_agent" ]] || fail "unexpected document entrypoint: $entrypoint"
[[ "$document_team" == "document_analysis_team" ]] || fail "unexpected document team: $document_team"
[[ "$team_id" == "email_triage_team" ]] || fail "unexpected email team: $team_id"
[[ "$steps" == "email_intake,triage,action_extraction,optional_attachment_analysis,approval_preparation" ]] || fail "unexpected team steps: $steps"
echo "PASS: registry resolution is correct"
echo "PASS: email team handoff skeleton is defined"

category_check="$(
docker exec -i "$BACKEND_CONTAINER" python - <<'PY'
from app.worker_runtime import (
    _categorize_attachment_failure,
    _categorize_execution_exception,
    _categorize_output_failure,
)

values = [
    _categorize_attachment_failure("attachment download is unavailable: TELEGRAM_BOT_TOKEN is missing"),
    _categorize_attachment_failure("failed to open pdf: bad file"),
    _categorize_output_failure("document_analysis_agent", "executor failed"),
    _categorize_output_failure("approval_prep_agent", "approval prep failed"),
    _categorize_execution_exception("approval_prep_agent", RuntimeError("boom")),
]
print("|".join(values))
PY
)"
[[ "$category_check" == "attachment_failure|extraction_failure|agent_execution_failure|approval_preparation_failure|approval_preparation_failure" ]] \
  || fail "failure category helpers returned unexpected values: $category_check"
echo "PASS: failure categories are distinguishable"

task_text="smoke-contract-$(date -u +%Y%m%dT%H%M%SZ)"
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
echo "PASS: contract smoke task created"

deadline=$((SECONDS + WORKER_WAIT_TIMEOUT_SECONDS))
last_status=""
last_result_text=""
while (( SECONDS < deadline )); do
  response="$(curl -fsS "$API_BASE_URL/tasks/$task_id")" || fail "GET /tasks/{task_id} failed"
  last_status="$(
    printf '%s' "$response" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("status") or "")'
  )"
  last_result_text="$(
    printf '%s' "$response" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("result_text") or "")'
  )"
  if [[ "$last_status" == "done" ]]; then
    [[ -n "$last_result_text" ]] || fail "task reached done but result_text is empty"
    break
  fi
  if [[ "$last_status" == "failed" ]]; then
    fail "document contract smoke task failed"
  fi
  sleep "$WORKER_POLL_INTERVAL_SECONDS"
done
[[ "$last_status" == "done" ]] || fail "task did not reach done within timeout"
echo "PASS: document contract flow reached done"

worker_logs="$(docker compose -f infra/docker-compose.yml logs --tail=200 worker)"
printf '%s\n' "$worker_logs" | grep -q "event=agent_route_resolved task_id=$task_id task_type=document_analysis agent_id=document_analysis_agent team_id=document_analysis_team" \
  || fail "agent route resolution log not found"
echo "PASS: agent route resolution logged"
printf '%s\n' "$worker_logs" | grep -q "event=agent_input_built task_id=$task_id agent_id=document_analysis_agent team_id=document_analysis_team" \
  || fail "agent input contract build log not found"
echo "PASS: input contract build logged"
printf '%s\n' "$worker_logs" | grep -q "event=agent_output_normalized task_id=$task_id agent_id=document_analysis_agent team_id=document_analysis_team success=True" \
  || fail "output contract normalization log not found"
echo "PASS: output contract normalization logged"
printf '%s\n' "$worker_logs" | grep -q "event=task_finalized task_id=$task_id team_id=document_analysis_team agent_id=document_analysis_agent final_status=done" \
  || fail "structured completion log not found"
printf '%s\n' "$worker_logs" | grep -q "event=task_finalized task_id=$task_id team_id=document_analysis_team agent_id=document_analysis_agent final_status=done delivery_status=none" \
  || fail "structured completion log does not include delivery status"
echo "PASS: structured completion log is present"

approval_response="$(
  curl -fsS \
    -X POST "$API_BASE_URL/tasks/$task_id/approvals" \
    -H "Content-Type: application/json" \
    -d '{"summary":"Review proposed client response","proposed_action":"Hold outbound action until approval","structured_result":{"result_type":"approval_request"},"handoff":"await_human_approval"}'
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

echo "SMOKE CONTRACT EXECUTION PASSED"
