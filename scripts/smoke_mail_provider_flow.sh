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
  [[ "$worker_running" != "true" ]] || fail "mail provider smoke requires ai_worker to be stopped: $WORKER_CONTAINER"
fi
echo "PASS: compose worker is not running"

existing_manual_worker_pids="$(list_backend_worker_runtime_pids)"
[[ -z "$existing_manual_worker_pids" ]] || fail "mail provider smoke requires no existing manual worker inside backend (found pids: $existing_manual_worker_pids)"
echo "PASS: no manual worker is running inside backend"

docker exec "$REDIS_CONTAINER" redis-cli DEL "$TASK_QUEUE_NAME" >/dev/null
echo "PASS: queue was reset for isolated provider smoke"

providers_response="$(curl -fsS "$API_BASE_URL/mail-providers")" || fail "GET /mail-providers failed"
printf '%s' "$providers_response" | python3 -c 'import json,sys; d=json.load(sys.stdin); providers=d.get("providers") or []; assert "fake" in providers and "mailru_imap" in providers' \
  || fail "provider registry does not expose fake and mailru_imap"
echo "PASS: adapter resolution registry is exposed"

run_id="$(date -u +%Y%m%dT%H%M%SZ)"
mailbox="ops-provider-$run_id@example.com"
curl -fsS \
  -X PUT "$API_BASE_URL/mailboxes/fake/$mailbox/policy" \
  -H "Content-Type: application/json" \
  -d '{"scope_mode":"all","triage_thresholds":{"light_min":25,"deep_min":60,"deep_with_attachment_min":40,"uncertain_band":0},"attachment_policy":{"download_for":["deep"],"max_attachments":5},"rollout_mode":"approval_only_for_deep"}' >/dev/null \
  || fail "failed to set deterministic provider smoke policy"
attachment_b64="$(printf 'Attachment body for provider smoke contract.' | base64 -w0)"
sync_response="$(
  curl -fsS \
    -X POST "$API_BASE_URL/mailboxes/sync" \
    -H "Content-Type: application/json" \
    -d "{\"provider\":\"fake\",\"mailbox\":\"$mailbox\",\"provider_options\":{\"messages\":[{\"uid\":2001,\"provider_message_id\":\"fake-ignore-$run_id\",\"internet_message_id\":\"<ignore-$run_id@example.com>\",\"from_address\":\"no-reply@vendor.example\",\"subject\":\"Automatic Reply: ticket\",\"snippet\":\"automatic reply\",\"labels\":[\"INBOX\"]},{\"uid\":2002,\"provider_message_id\":\"fake-light-$run_id\",\"internet_message_id\":\"<light-$run_id@example.com>\",\"from_address\":\"pm@example.net\",\"subject\":\"Request: review weekly status digest\",\"snippet\":\"Please review the weekly digest before tomorrow so we can prepare the next summary.\",\"labels\":[\"INBOX\"]},{\"uid\":2003,\"provider_message_id\":\"fake-deep-$run_id\",\"internet_message_id\":\"<deep-$run_id@example.com>\",\"from_address\":\"client@example.net\",\"subject\":\"Action required: approve invoice today\",\"snippet\":\"Please review the invoice and approve payment before the deadline tomorrow morning.\",\"labels\":[\"INBOX\",\"IMPORTANT\"],\"telegram_chat_id\":10001,\"reply_to_message_id\":1},{\"uid\":2004,\"provider_message_id\":\"fake-attach-$run_id\",\"internet_message_id\":\"<attach-$run_id@example.com>\",\"from_address\":\"legal@example.net\",\"subject\":\"Contract for review\",\"snippet\":\"Attached contract needs review and approval this week.\",\"labels\":[\"INBOX\"],\"telegram_chat_id\":10001,\"reply_to_message_id\":1,\"attachments\":[{\"attachment_id\":\"att-provider-1\",\"filename\":\"contract.txt\",\"mime_type\":\"text/plain\",\"file_size\":44,\"is_inline\":false,\"content_base64\":\"$attachment_b64\"}]},{\"uid\":2005,\"provider_message_id\":\"fake-attach-dup-$run_id\",\"internet_message_id\":\"<attach-$run_id@example.com>\",\"from_address\":\"legal@example.net\",\"subject\":\"Contract for review\",\"snippet\":\"Attached contract needs review and approval this week.\",\"labels\":[\"INBOX\"],\"attachments\":[{\"attachment_id\":\"att-provider-2\",\"filename\":\"contract-copy.txt\",\"mime_type\":\"text/plain\",\"file_size\":45,\"is_inline\":false,\"content_base64\":\"$attachment_b64\"}]}]}}"
)" || fail "POST /mailboxes/sync failed"

counts="$(
  printf '%s' "$sync_response" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("|".join(str(d.get(k)) for k in ("fetched_count","normalized_count","ignore_count","light_count","deep_count","uncertain_count","duplicate_count","task_count")))'
)"
[[ "$counts" == "5|5|1|1|2|0|1|2" ]] || fail "unexpected sync counts: $counts"
echo "PASS: fetch -> normalize -> intake reuse produced expected ignore/light/deep/dedupe counts"

backend_logs="$(docker compose -f "$COMPOSE_FILE" logs --tail=400 backend)"
printf '%s\n' "$backend_logs" | grep -q "event=mail_provider_sync_started provider=fake mailbox=$mailbox" \
  || fail "mail_provider_sync_started log not found"
printf '%s\n' "$backend_logs" | grep -q "event=mail_message_fetched provider=fake mailbox=$mailbox provider_message_id=2001" \
  || fail "mail_message_fetched log not found"
printf '%s\n' "$backend_logs" | grep -q "event=mail_message_normalized provider=fake mailbox=$mailbox provider_message_id=fake-attach-$run_id attachment_count=1" \
  || fail "mail_message_normalized log not found"
printf '%s\n' "$backend_logs" | grep -q "event=mail_message_skipped provider=fake mailbox=$mailbox provider_message_id=fake-light-$run_id reason=light" \
  || fail "mail_message_skipped log not found"
printf '%s\n' "$backend_logs" | grep -q "event=mail_checkpoint_updated provider=fake mailbox=$mailbox" \
  || fail "mail_checkpoint_updated log not found"
printf '%s\n' "$backend_logs" | grep -q "event=mail_provider_sync_completed provider=fake mailbox=$mailbox fetched_count=5 normalized_count=5 task_count=2" \
  || fail "mail_provider_sync_completed log not found"
echo "PASS: provider sync structured logs are present"

checkpoint_response="$(curl -fsS "$API_BASE_URL/mailboxes/fake/$mailbox/checkpoint")" || fail "GET checkpoint failed"
checkpoint_uid="$(
  printf '%s' "$checkpoint_response" | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("checkpoint") or {}).get("last_uid") or "")'
)"
[[ "$checkpoint_uid" == "2005" ]] || fail "checkpoint last_uid expected 2005, got: $checkpoint_uid"
echo "PASS: mailbox checkpoint updated"

lookup="$(
  docker exec -i "$BACKEND_CONTAINER" python3 - <<PY
from app.database import SessionLocal
from app.models import EmailSource

db = SessionLocal()
items = db.query(EmailSource).filter(EmailSource.provider == "fake", EmailSource.mailbox == "$mailbox").order_by(EmailSource.id.asc()).all()
rows = []
for item in items[-5:]:
    rows.append(f"{item.provider_message_id}:{item.routing_decision}:{item.task_id or ''}:{item.duplicate_of_email_id or ''}")
print("|".join(rows))
db.close()
PY
)"
printf '%s' "$lookup" | grep -q "fake-ignore-$run_id:ignore::" || fail "ignore message routing missing"
printf '%s' "$lookup" | grep -q "fake-light-$run_id:light::" || fail "light message routing missing"
printf '%s' "$lookup" | grep -q "fake-deep-$run_id:deep:" || fail "deep message routing missing"
printf '%s' "$lookup" | grep -q "fake-attach-$run_id:deep:" || fail "attachment deep routing missing"
printf '%s' "$lookup" | grep -q "fake-attach-dup-$run_id:ignore::" || fail "duplicate routing missing"
echo "PASS: intake reuse persisted expected routing decisions"

worker_log_file="${TMPDIR:-/tmp}/smoke-mail-provider.$$.log"
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
  python -m app.worker_runtime --max-tasks 2 >"$worker_log_file" 2>&1 &
worker_pid="$!"
sleep "$WORKER_STARTUP_SLEEP_SECONDS"

deep_task_ids="$(
  docker exec -i "$BACKEND_CONTAINER" python3 - <<PY
from app.database import SessionLocal
from app.models import EmailSource

db = SessionLocal()
items = db.query(EmailSource).filter(EmailSource.provider == "fake", EmailSource.provider_message_id.in_(["fake-deep-$run_id", "fake-attach-$run_id"])).order_by(EmailSource.id.asc()).all()
print("|".join(item.task_id or "" for item in items))
db.close()
PY
)"
IFS='|' read -r deep_task_id attachment_task_id <<<"$deep_task_ids"
[[ -n "$deep_task_id" ]] || fail "deep task id missing"
[[ -n "$attachment_task_id" ]] || fail "attachment task id missing"

for task_id in "$deep_task_id" "$attachment_task_id"; do
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
      fail "provider deep task $task_id reached failed"
    fi
    sleep "$WORKER_POLL_INTERVAL_SECONDS"
  done
  [[ "$last_status" == "done" ]] || fail "provider deep task $task_id did not reach done within timeout"
done
echo "PASS: deep tasks were created and processed"

worker_logs="$(cat "$worker_log_file")"
printf '%s\n' "$worker_logs" | grep -q "event=mail_attachment_download_started provider=fake mailbox=$mailbox" \
  || fail "attachment download start log not found"
printf '%s\n' "$worker_logs" | grep -q "event=mail_attachment_download_completed provider=fake mailbox=$mailbox" \
  || fail "attachment download completion log not found"
echo "PASS: provider-agnostic attachment download contract executed"

echo "SMOKE MAIL PROVIDER FLOW PASSED"
