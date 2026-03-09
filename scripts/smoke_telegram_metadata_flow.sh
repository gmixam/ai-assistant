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
FAKE_CHAT_ID="${FAKE_CHAT_ID:-123456789}"
FAKE_USER_ID="${FAKE_USER_ID:-987654321}"
FAKE_MESSAGE_ID="${FAKE_MESSAGE_ID:-42}"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

require_cmd curl
require_cmd python3

task_text="smoke-telegram-meta-$(date -u +%Y%m%dT%H%M%SZ)"
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

task_get="$(curl -fsS "$API_BASE_URL/tasks/$task_id")" || fail "GET /tasks/{task_id} failed"

validate="$(
  printf '%s' "$task_get" | EXPECT_CHAT_ID="$FAKE_CHAT_ID" EXPECT_USER_ID="$FAKE_USER_ID" EXPECT_MESSAGE_ID="$FAKE_MESSAGE_ID" python3 -c '
import os, sys, json
d = json.load(sys.stdin)
ok = (
    str(d.get("telegram_chat_id")) == os.environ["EXPECT_CHAT_ID"] and
    str(d.get("telegram_user_id")) == os.environ["EXPECT_USER_ID"] and
    str(d.get("telegram_message_id")) == os.environ["EXPECT_MESSAGE_ID"] and
    str(d.get("reply_to_message_id")) == os.environ["EXPECT_MESSAGE_ID"]
)
print("ok" if ok else "bad")
'
)"
[[ "$validate" == "ok" ]] || fail "telegram metadata not persisted correctly"

echo "PASS: telegram metadata persisted"
echo "SMOKE TELEGRAM METADATA PASSED"
