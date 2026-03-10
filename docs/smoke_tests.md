# Smoke Tests

## What this smoke-test validates
`make smoke` validates queue/persistence behavior in isolated debug conditions:
- `POST /tasks` creates a task.
- Task can be fetched via `GET /tasks/{task_id}`.
- Task status is `queued`.
- `task_id` is present in Redis queue.
- `task_id` is present in PostgreSQL.

`make smoke-worker` validates normal operation mode with dedicated `ai_worker`:
- backend accepts a task
- `ai_worker` consumes it
- task reaches the expected final state
- result or error text is persisted as expected

## How to run
From repository root:
```bash
make up
make smoke-normal
make smoke
```

Recommended mode-specific entry points:
- `make smoke-normal`:
  brings `ai_worker` up and runs normal-mode worker smoke
- `make smoke`:
  stops `ai_worker` first and runs isolated queue/persistence smoke
- `make smoke-worker-debug`:
  stops `ai_worker` first and runs isolated one-shot worker smoke

For final normal-operation readiness, the manual Telegram document E2E remains the decisive check because it validates:
- real Telegram file intake
- real attachment download from Telegram API
- real worker execution path in `ai_worker`
- real Telegram reply delivery

Optional environment overrides:
- `API_BASE_URL` (default: `http://localhost:8000`)
- `TASK_QUEUE_NAME` (default: `tasks:queue`)
- `REDIS_CONTAINER` (default: `ai_redis`)
- `POSTGRES_CONTAINER` (default: `ai_postgres`)

## Success criteria
Successful run prints:
- `PASS: backend healthcheck is reachable`
- `PASS: compose worker is not running`
- `PASS: no manual worker is running inside backend`
- `PASS: task created`
- `PASS: task returned by API`
- `PASS: task status is queued`
- `PASS: task found in Redis queue`
- `PASS: task found in PostgreSQL`
- `SMOKE TEST PASSED`

For worker lifecycle smoke:
- `PASS: backend healthcheck is reachable`
- `PASS: compose worker is running`
- `PASS: no manual worker is running inside backend`
- `PASS: worker smoke task created`
- `PASS: worker lifecycle reached done`
- `PASS: worker result_text is present`
- `SMOKE WORKER TEST PASSED`

Normal mode:
- `make smoke-worker` expects the dedicated `ai_worker` Compose service to be already running.
- `make smoke-normal` is an alias for the same normal-mode worker smoke.
- `make smoke-normal` is the deterministic entry point because it starts `ai_worker` first.

Provider-stub smoke (expected controlled failure):
```bash
WORKER_MODE=debug TASK_EXECUTOR=openai EXPECTED_FINAL_STATUS=failed ./scripts/smoke_worker_flow.sh
WORKER_MODE=debug TASK_EXECUTOR=deepseek EXPECTED_FINAL_STATUS=failed ./scripts/smoke_worker_flow.sh
WORKER_MODE=debug TASK_EXECUTOR=kimi EXPECTED_FINAL_STATUS=failed ./scripts/smoke_worker_flow.sh
```
Expected:
- `PASS: worker lifecycle reached failed`
- `PASS: worker error_text is present`
- `SMOKE WORKER TEST PASSED`

Debug mode:
- provider override smokes run a temporary one-shot worker inside `ai_backend` because they need temporary env overrides that should not mutate the normal `ai_worker` service.

OpenAI helper targets:
```bash
make smoke-worker-openai-no-key   # expected failed + error_text
make smoke-worker-openai          # expected done + result_text (requires OPENAI_API_KEY)
make smoke-worker-debug           # isolated one-shot worker in debug mode
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

Note:
- `make smoke-telegram-delivery` is a diagnostic smoke and intentionally starts a one-shot debug worker with temporary env overrides.
- It requires `ai_worker` to be stopped and no manual worker to be running inside `ai_backend`.
- The target enforces this by stopping `ai_worker` before the script runs.

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

Final MVP document-analysis readiness gate:
1. Normal stack is up via `make up`.
2. `make smoke-worker` passes with dedicated `ai_worker`.
3. `make smoke` passes with `ai_worker` stopped and no stray manual worker.
4. Manual Telegram document scenario passes end-to-end with `delivery_status=delivered`.
5. Task API confirms attachment download/extraction diagnostics for the tested document.

Manual delivery diagnostics scenarios:
1. Successful delivery path -> expect `delivery_status=delivered`, non-null `delivered_at`.
2. Delivery failure path (e.g. invalid chat or Telegram API issue) -> expect `delivery_status=failed` and non-empty `delivery_error`.

## What to do on fail
1. Check backend logs:
```bash
cd infra && docker compose logs --tail=100 backend
```
2. Check worker logs:
```bash
cd infra && docker compose logs --tail=100 worker
```
3. Verify PostgreSQL, Redis, backend, and worker containers are running:
```bash
cd infra && docker compose ps
```
4. Re-run:
```bash
make smoke
```

## Mode split
Normal mode:
- `make up`
- `make smoke-normal`
- `make smoke-worker` only if `ai_worker` is already running
- PASS requires running `ai_worker` and no manual worker inside `ai_backend`

Debug mode:
- run `make smoke`, `make smoke-worker-debug`, `make smoke-worker-openai-no-key`, or `make smoke-telegram-delivery`
- PASS requires no running `ai_worker` and no pre-existing manual worker inside `ai_backend`
- these targets stop `ai_worker` before execution to keep the run isolated

## Diagnose one task end-to-end
For one task id, the fastest normal-operation inspection path is grep by `task_id=` in worker logs:

```bash
TASK_ID=<task_id>
docker compose -f infra/docker-compose.yml logs --tail=200 worker | grep "task_id=$TASK_ID"
```

Useful event names:
- `event=task_dequeued`
- `event=worker_task_started`
- `event=attachment_download_started`
- `event=attachment_download_completed`
- `event=text_extraction_started`
- `event=text_extraction_completed`
- `event=ai_execution_started`
- `event=ai_execution_completed`
- `event=telegram_delivery_started`
- `event=telegram_delivery_completed`
- `event=task_finalized`

If the task fails, inspect:
- `event=attachment_download_failed`
- `event=text_extraction_failed`
- `event=ai_execution_failed`
- `event=telegram_delivery_failed`
