# Smoke Tests

## What this smoke-test validates
`make smoke` validates the current Task Flow end-to-end:
- `POST /tasks` creates a task.
- Task can be fetched via `GET /tasks/{task_id}`.
- Task status is `queued`.
- `task_id` is present in Redis queue.
- `task_id` is present in PostgreSQL.

## How to run
From repository root:
```bash
make smoke
make smoke-worker
```

Optional environment overrides:
- `API_BASE_URL` (default: `http://localhost:8000`)
- `TASK_QUEUE_NAME` (default: `tasks:queue`)
- `REDIS_CONTAINER` (default: `ai_redis`)
- `POSTGRES_CONTAINER` (default: `ai_postgres`)

## Success criteria
Successful run prints:
- `PASS: task created`
- `PASS: task returned by API`
- `PASS: task status is queued`
- `PASS: task found in Redis queue`
- `PASS: task found in PostgreSQL`
- `SMOKE TEST PASSED`

For worker lifecycle smoke:
- `PASS: worker smoke task created`
- `PASS: worker lifecycle reached done`
- `PASS: worker result_text is present`
- `SMOKE WORKER TEST PASSED`

Provider-stub smoke (expected controlled failure):
```bash
TASK_EXECUTOR=openai EXPECTED_FINAL_STATUS=failed make smoke-worker
TASK_EXECUTOR=deepseek EXPECTED_FINAL_STATUS=failed make smoke-worker
TASK_EXECUTOR=kimi EXPECTED_FINAL_STATUS=failed make smoke-worker
```
Expected:
- `PASS: worker lifecycle reached failed`
- `PASS: worker error_text is present`
- `SMOKE WORKER TEST PASSED`

OpenAI helper targets:
```bash
make smoke-worker-openai-no-key   # expected failed + error_text
make smoke-worker-openai          # expected done + result_text (requires OPENAI_API_KEY)
```

Telegram metadata persistence smoke:
```bash
make smoke-telegram-metadata
```

Telegram delivery reliability smoke:
```bash
make smoke-telegram-delivery
```
Validates:
- task execution reaches `done`
- Telegram delivery state reaches `failed` when Telegram API is unavailable
- `delivery_error` is persisted

Task attachment metadata persistence smoke:
```bash
make smoke-task-attachment
```

Local attachment text extraction smoke:
```bash
make smoke-attachment-extract-local
# optional PDF extraction check:
PDF_SAMPLE_PATH=/absolute/path/to/sample.pdf make smoke-attachment-extract-local
```
This smoke also validates truncation guardrail on oversized extracted content.

Manual Telegram intake scenarios:
1. Text only:
```text
Send plain text message -> expect task created.
```
2. File with caption:
```text
Send Telegram document with caption -> expect task created immediately.
```
3. File without caption + follow-up text:
```text
Send Telegram document without caption -> bot asks for instruction.
Send next text message -> expect task created with same attachment.
```

Manual file-reading scenarios (worker):
1. `text/plain` document + caption -> expect `download_status=downloaded` and final task result.
2. `application/pdf` document + caption -> expect extracted text used in execution.
3. `.docx` document + caption -> expect extracted text used in execution.
4. Large document -> expect successful processing with `was_truncated=true` and `sent_text_length < extracted_text_length`.

Manual delivery diagnostics scenarios:
1. Successful delivery path -> expect `delivery_status=delivered`, non-null `delivered_at`.
2. Delivery failure path (e.g. invalid chat or Telegram API issue) -> expect `delivery_status=failed` and non-empty `delivery_error`.

## What to do on fail
1. Check backend logs:
```bash
cd infra && docker compose logs --tail=100 backend
```
2. Verify PostgreSQL and Redis containers are running:
```bash
cd infra && docker compose ps
```
3. Re-run:
```bash
make smoke
```
