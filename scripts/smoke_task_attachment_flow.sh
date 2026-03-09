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
FAKE_FILE_ID="${FAKE_FILE_ID:-telegram-file-id-smoke}"
FAKE_FILENAME="${FAKE_FILENAME:-sample.pdf}"
FAKE_MIME_TYPE="${FAKE_MIME_TYPE:-application/pdf}"
FAKE_FILE_SIZE="${FAKE_FILE_SIZE:-2048}"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

require_cmd curl
require_cmd python3

task_text="smoke-attachment-$(date -u +%Y%m%dT%H%M%SZ)"
post_response="$(
  curl -fsS \
    -X POST "$API_BASE_URL/tasks" \
    -H "Content-Type: application/json" \
    -d "{\"input_text\":\"$task_text\",\"telegram_chat_id\":$FAKE_CHAT_ID,\"telegram_user_id\":$FAKE_USER_ID,\"attachment\":{\"telegram_file_id\":\"$FAKE_FILE_ID\",\"filename\":\"$FAKE_FILENAME\",\"mime_type\":\"$FAKE_MIME_TYPE\",\"file_size\":$FAKE_FILE_SIZE,\"telegram_chat_id\":$FAKE_CHAT_ID,\"telegram_user_id\":$FAKE_USER_ID}}"
)" || fail "POST /tasks with attachment failed"

task_id="$(
  printf '%s' "$post_response" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("task_id") or d.get("id") or "")'
)"
[[ -n "$task_id" ]] || fail "task_id is missing"

task_get="$(curl -fsS "$API_BASE_URL/tasks/$task_id")" || fail "GET /tasks/{task_id} failed"

validate="$(
  printf '%s' "$task_get" \
    | EXPECT_FILE_ID="$FAKE_FILE_ID" EXPECT_FILENAME="$FAKE_FILENAME" EXPECT_MIME="$FAKE_MIME_TYPE" EXPECT_SIZE="$FAKE_FILE_SIZE" EXPECT_CHAT_ID="$FAKE_CHAT_ID" EXPECT_USER_ID="$FAKE_USER_ID" python3 -c '
import json
import os
import sys

d = json.load(sys.stdin)
attachments = d.get("attachments") or []
if not attachments:
    print("bad")
    raise SystemExit(0)
a = attachments[0]
ok = (
    str(a.get("telegram_file_id")) == os.environ["EXPECT_FILE_ID"] and
    str(a.get("filename")) == os.environ["EXPECT_FILENAME"] and
    str(a.get("mime_type")) == os.environ["EXPECT_MIME"] and
    str(a.get("file_size")) == os.environ["EXPECT_SIZE"] and
    str(a.get("telegram_chat_id")) == os.environ["EXPECT_CHAT_ID"] and
    str(a.get("telegram_user_id")) == os.environ["EXPECT_USER_ID"]
)
print("ok" if ok else "bad")
'
)"
[[ "$validate" == "ok" ]] || fail "task attachment metadata not persisted correctly"

echo "PASS: task attachment metadata persisted"
echo "SMOKE TASK ATTACHMENT PASSED"
