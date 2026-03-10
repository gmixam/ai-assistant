# Task Execution System - Step 7 (Telegram End-to-End Delivery)

## Goal
Complete MVP end-to-end user flow:

`Telegram -> Bot -> Backend -> PostgreSQL -> Redis -> Worker -> OpenAI -> Telegram`

## Current status
Ready for normal operation mode with dedicated Compose services:
- `ai_bot` handles Telegram intake.
- `ai_backend` handles API, persistence, and queue enqueue.
- `ai_worker` handles queue consumption, execution, and Telegram delivery.

Normal operation mode:
- `ai_worker` is the standard runtime.
- manual `docker exec ... python -m app.worker_runtime` is diagnostic/fallback only.

What is already working in the MVP pipeline:
- Telegram task intake through bot
- task persistence in PostgreSQL
- Redis queue handoff
- worker task execution
- Telegram result delivery
- attachment metadata persistence

What still requires manual E2E confirmation in a live Telegram environment:
- real Telegram `document -> analysis -> reply` scenario against the currently deployed bot token and chat
- result quality of the selected AI executor for client-facing summaries

## What changed
- Task model extended with Telegram metadata (nullable):
  - `telegram_chat_id`
  - `telegram_user_id`
  - `telegram_message_id`
  - `reply_to_message_id`
- Bot now sends Telegram metadata in `POST /tasks`.
- Bot intake supports file-first flow for Telegram `document` attachments.
- Backend persists metadata and returns it in task responses.
- Backend accepts optional task attachment metadata and stores it in `task_attachments`.
- Worker performs outbound Telegram delivery after processing:
  - on `done`: sends `result_text`
  - on `failed`: sends `error_text`
- Task now stores Telegram delivery diagnostics:
  - `delivery_status` (`pending`, `delivered`, `failed`)
  - `delivered_at`
  - `delivery_error`

Attachment metadata stored (MVP):
- `telegram_file_id`
- `filename`
- `mime_type`
- `file_size`
- `telegram_chat_id`
- `telegram_user_id`
- `task_id` (relation to task)

## Delivery strategy
Chosen MVP-safe approach:
- worker sends message directly via Telegram Bot API.

Why:
- keeps architecture simple and decoupled from bot runtime internals
- no additional event bus or callback service required
- reversible and minimal changes

## Controlled behavior
- If task has no `telegram_chat_id`: worker logs skip, does not crash.
- If `delivery_status=delivered`: worker skips re-delivery.
- If Telegram delivery fails: worker records `delivery_status=failed` + `delivery_error` and keeps loop alive.
- Telegram delivery failures are logged and do not break worker loop.

## Env used for Telegram delivery
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_API_BASE_URL` (default: `https://api.telegram.org`)
- `TELEGRAM_DELIVERY_TIMEOUT_SECONDS` (default: `15`)

## Smoke checks
Base:
```bash
make smoke
make smoke-worker
```

Metadata persistence:
```bash
make smoke-telegram-metadata
make smoke-telegram-delivery
```

## Manual Telegram E2E test
1. Ensure `bot`, `backend`, `worker`, `postgres`, `redis` are running.
2. Use `ai_worker` as the normal worker runtime.
3. In Telegram, validate scenarios:
   - text only: send plain text (without `/task`)
   - file with caption: send `document` with caption instruction
   - file without caption: send `document` without caption, then send text instruction
   - legacy: send `/task your prompt here`
4. Expect for all scenarios:
   - immediate bot ack with task id
   - follow-up message from worker delivery with final result (or error)
5. For file scenarios, verify with API:
   - `GET /tasks/{task_id}` includes `attachments` with file metadata.
6. For delivery diagnostics, verify with API:
   - `delivery_status=delivered` on successful Telegram send
   - `delivery_status=failed` with `delivery_error` on delivery errors.

## Final E2E success checklist
Use this checklist for the main MVP case `Telegram document -> AI analysis -> Telegram reply`:
1. `docker compose -f infra/docker-compose.yml ps` shows `bot`, `backend`, `worker`, `postgres`, `redis` running.
2. Send a supported Telegram document (`txt`, `pdf`, or `docx`) with a clear analysis instruction in caption or follow-up text.
3. Bot immediately returns task acknowledgement with task id.
4. `GET /tasks/{task_id}` shows:
   - task status moves `queued -> processing -> done`
   - attachment row exists
   - `download_status=downloaded`
   - non-empty `local_path`
5. Worker sends Telegram reply back to the same chat.
6. Final task payload shows:
   - non-empty `result_text`
   - `delivery_status=delivered`
   - non-null `delivered_at`
7. If the document is large:
   - task still completes
   - attachment diagnostics may show truncation without task failure

Checklist result interpretation:
- all items pass -> MVP normal-operation document analysis pipeline is operational
- task reaches `failed` with clear `error_text` -> pipeline is observable but the failing stage needs follow-up
- no Telegram reply with `status=done` -> investigate delivery path and `delivery_status`

Debug/fallback only:
- manual `docker exec -it ai_backend python -m app.worker_runtime` should be used only for diagnostics or temporary recovery, not as the normal operating mode.

## Minimal observability improvements
If E2E diagnosis still feels too manual, the next minimal logging improvements should be:
- log `task_id`, `attachment_count`, and final `delivery_status` in one worker completion line
- log `telegram_chat_id` and `task_id` on delivery attempt start
- log attachment filename + `download_status` transition per attachment
- add one grep-friendly log line for `task_id=<id> final_status=<status> delivery_status=<status>`
