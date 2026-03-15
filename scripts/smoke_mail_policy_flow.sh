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
REDIS_CONTAINER="${REDIS_CONTAINER:-ai_redis}"
WORKER_CONTAINER="${WORKER_CONTAINER:-ai_worker}"
TASK_QUEUE_NAME="${TASK_QUEUE_NAME:-tasks:queue}"
COMPOSE_FILE="${COMPOSE_FILE:-infra/docker-compose.yml}"

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

lookup_email() {
  local provider_message_id="$1"
  docker exec -i "$BACKEND_CONTAINER" python3 - <<PY
from app.database import SessionLocal
from app.models import EmailSource
db = SessionLocal()
item = db.query(EmailSource).filter(EmailSource.provider_message_id == "$provider_message_id").first()
if item is None:
    print("||||||||")
else:
    print("|".join([
        str(item.id),
        item.routing_decision or "",
        item.decision_source or "",
        item.rollout_mode or "",
        item.uncertain_reason or "",
        item.task_id or "",
        item.reason_codes_json or "[]",
        item.rule_hits_json or "[]",
    ]))
db.close()
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
  [[ "$worker_running" != "true" ]] || fail "mail policy smoke requires ai_worker to be stopped: $WORKER_CONTAINER"
fi
echo "PASS: compose worker is not running"

docker exec "$REDIS_CONTAINER" redis-cli DEL "$TASK_QUEUE_NAME" >/dev/null
echo "PASS: queue was reset for isolated policy smoke"

run_id="$(date -u +%Y%m%dT%H%M%SZ)"
mailbox="policy-$run_id@example.com"

policy_response="$(
  curl -fsS \
    -X PUT "$API_BASE_URL/mailboxes/fake/$mailbox/policy" \
    -H "Content-Type: application/json" \
    -d '{"scope_mode":"all","trusted_domains":["vip.example.com"],"blocked_senders":["blocked@example.net"],"watch_domains":["watch.example.net"],"priority_rules":[{"contains":"vip","boost":10}],"triage_thresholds":{"light_min":25,"deep_min":60,"deep_with_attachment_min":40,"uncertain_band":3},"attachment_policy":{"download_for":["deep"],"max_attachments":5},"rollout_mode":"observe_only"}'
)" || fail "PUT policy failed"
printf '%s' "$policy_response" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["rollout_mode"]=="observe_only"' || fail "policy rollout_mode mismatch"
echo "PASS: mailbox policy persisted"

sync_observe="$(
  curl -fsS \
    -X POST "$API_BASE_URL/mailboxes/sync" \
    -H "Content-Type: application/json" \
    -d "{\"provider\":\"fake\",\"mailbox\":\"$mailbox\",\"provider_options\":{\"messages\":[{\"uid\":3001,\"provider_message_id\":\"observe-deep-$run_id\",\"internet_message_id\":\"<observe-deep-$run_id@example.com>\",\"from_address\":\"vip@vip.example.com\",\"subject\":\"VIP action required today\",\"snippet\":\"Please approve the contract today.\",\"labels\":[\"INBOX\"]},{\"uid\":3002,\"provider_message_id\":\"blocked-$run_id\",\"internet_message_id\":\"<blocked-$run_id@example.com>\",\"from_address\":\"blocked@example.net\",\"subject\":\"Action required\",\"snippet\":\"Please review.\",\"labels\":[\"INBOX\"]},{\"uid\":3003,\"provider_message_id\":\"watch-$run_id\",\"internet_message_id\":\"<watch-$run_id@example.com>\",\"from_address\":\"ceo@watch.example.net\",\"subject\":\"Review soon\",\"snippet\":\"Please review soon.\",\"labels\":[\"INBOX\"]}]}}"
)" || fail "POST observe sync failed"
counts="$(
  printf '%s' "$sync_observe" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("|".join(str(d.get(k)) for k in ("ignore_count","light_count","deep_count","uncertain_count","task_count")))'
)"
[[ "$counts" == "1|0|1|1|0" ]] || fail "unexpected observe sync counts: $counts"
echo "PASS: observe-only rollout and uncertain path behaved as expected"

observe_lookup="$(lookup_email "observe-deep-$run_id")"
blocked_lookup="$(lookup_email "blocked-$run_id")"
watch_lookup="$(lookup_email "watch-$run_id")"
printf '%s\n' "$observe_lookup" | grep -q "|deep|rollout_mode|observe_only|||" || fail "observe-only deep audit missing"
printf '%s\n' "$blocked_lookup" | grep -q "|ignore|policy_blocked|observe_only|||" || fail "blocked sender audit missing"
printf '%s\n' "$watch_lookup" | grep -q "|uncertain|policy_uncertain|observe_only|watch_domain_requires_review||" || fail "uncertain watch audit missing"
echo "PASS: policy audit fields are persisted"

curl -fsS \
  -X POST "$API_BASE_URL/mailboxes/sync" \
  -H "Content-Type: application/json" \
  -d "{\"provider\":\"fake\",\"mailbox\":\"$mailbox\",\"provider_options\":{\"messages\":[{\"uid\":3004,\"provider_message_id\":\"light-$run_id\",\"internet_message_id\":\"<light-$run_id@example.com>\",\"from_address\":\"pm@example.net\",\"subject\":\"Request: review weekly status digest\",\"snippet\":\"Please review the weekly digest before tomorrow so we can prepare the next summary.\",\"labels\":[\"INBOX\"]}]}}" >/dev/null \
  || fail "POST light sync failed"
light_lookup="$(lookup_email "light-$run_id")"
light_email_id="$(printf '%s' "$light_lookup" | cut -d'|' -f1)"
printf '%s\n' "$light_lookup" | grep -q "|light|policy_thresholds|observe_only|||" || fail "light routing audit missing"

override_light="$(
  curl -fsS \
    -X POST "$API_BASE_URL/email-sources/$light_email_id/override" \
    -H "Content-Type: application/json" \
    -d '{"routing_decision":"deep","decided_by":"policy-smoke","comment":"escalate to deep"}'
)" || fail "POST light->deep override failed"
override_task_id="$(printf '%s' "$override_light" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("task_id") or "")')"
override_decision_source="$(printf '%s' "$override_light" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("decision_source") or "")')"
[[ -n "$override_task_id" ]] || fail "light->deep override did not create task"
[[ "$override_decision_source" == "manual_override" ]] || fail "light->deep override did not set manual decision source"
echo "PASS: light->deep manual override created task"

override_deep_to_light="$(
  curl -fsS \
    -X POST "$API_BASE_URL/email-sources/$light_email_id/override" \
    -H "Content-Type: application/json" \
    -d '{"routing_decision":"light","decided_by":"policy-smoke","comment":"downgrade after review"}'
)" || fail "POST deep->light override failed"
printf '%s' "$override_deep_to_light" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["routing_decision"]=="light"' || fail "deep->light override did not persist"
echo "PASS: deep->light manual override persisted"

ignore_override="$(
  curl -fsS \
    -X POST "$API_BASE_URL/email-sources/$(printf '%s' "$blocked_lookup" | cut -d'|' -f1)/override" \
    -H "Content-Type: application/json" \
    -d '{"routing_decision":"light","decided_by":"policy-smoke","comment":"review blocked sender manually"}'
)" || fail "POST ignore->light override failed"
printf '%s' "$ignore_override" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["routing_decision"]=="light"' || fail "ignore->light override did not persist"
echo "PASS: ignore->light manual override persisted"

policy_response_full="$(
  curl -fsS \
    -X PUT "$API_BASE_URL/mailboxes/fake/$mailbox/policy" \
    -H "Content-Type: application/json" \
    -d '{"scope_mode":"all","trusted_domains":["vip.example.com"],"blocked_senders":["blocked@example.net"],"watch_domains":["watch.example.net"],"priority_rules":[{"contains":"vip","boost":10}],"triage_thresholds":{"light_min":25,"deep_min":60,"deep_with_attachment_min":40,"uncertain_band":3},"attachment_policy":{"download_for":["deep"],"max_attachments":5},"rollout_mode":"full_mode"}'
)" || fail "PUT full_mode policy failed"
printf '%s' "$policy_response_full" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["rollout_mode"]=="full_mode"' || fail "policy full_mode mismatch"

full_sync="$(
  curl -fsS \
    -X POST "$API_BASE_URL/mailboxes/sync" \
    -H "Content-Type: application/json" \
    -d "{\"provider\":\"fake\",\"mailbox\":\"$mailbox\",\"provider_options\":{\"messages\":[{\"uid\":3005,\"provider_message_id\":\"full-deep-$run_id\",\"internet_message_id\":\"<full-deep-$run_id@example.com>\",\"from_address\":\"vip@vip.example.com\",\"subject\":\"VIP contract approval today\",\"snippet\":\"Please approve the contract today.\",\"labels\":[\"INBOX\"]}]}}"
)" || fail "POST full_mode sync failed"
printf '%s' "$full_sync" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["task_count"]==1 and d["deep_count"]==1' || fail "full_mode deep sync did not create task"
echo "PASS: full_mode deep path created task"

backend_logs="$(docker compose -f "$COMPOSE_FILE" logs --tail=500 backend)"
printf '%s\n' "$backend_logs" | grep -q "event=mail_policy_applied provider=fake mailbox=$mailbox provider_message_id=observe-deep-$run_id decision=deep decision_source=rollout_mode rollout_mode=observe_only" \
  || fail "mail_policy_applied log not found"
printf '%s\n' "$backend_logs" | grep -q "event=mail_routing_finalized provider=fake mailbox=$mailbox provider_message_id=blocked-$run_id routing_decision=ignore decision_source=policy_blocked rollout_mode=observe_only" \
  || fail "mail_routing_finalized log not found"
printf '%s\n' "$backend_logs" | grep -q "event=mail_manual_override_applied email_source_id=$light_email_id from_decision=light to_decision=deep decided_by=policy-smoke" \
  || fail "manual override log not found"
echo "PASS: policy and override structured logs are present"

echo "SMOKE MAIL POLICY FLOW PASSED"
