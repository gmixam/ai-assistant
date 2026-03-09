# Task Execution System - Step 7 (Telegram End-to-End Delivery)

## Goal
Complete MVP end-to-end user flow:

`Telegram -> Bot -> Backend -> PostgreSQL -> Redis -> Worker -> OpenAI -> Telegram`

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
- If `TELEGRAM_BOT_TOKEN` is missing: worker logs skip, does not crash.
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
```

## Manual Telegram E2E test
1. Ensure `bot`, `backend`, `postgres`, `redis` are running.
2. Start worker in environment where `TELEGRAM_BOT_TOKEN` is available.
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
