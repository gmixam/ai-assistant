# MVP Document Analysis Readiness

## Normal operation mode
The standard runtime mode is Docker Compose with dedicated services:
- `ai_bot`
- `ai_backend`
- `ai_worker`
- `ai_postgres`
- `ai_redis`

`ai_worker` is the only standard worker runtime in normal operation.

Diagnostic/fallback mode:
- manual `docker exec -it ai_backend python -m app.worker_runtime`
- use only for debugging, temporary recovery, or env-override smoke checks

## Ready now
Current MVP capabilities:
- Telegram text and document intake through bot
- backend task creation and PostgreSQL persistence
- Redis queue handoff to worker
- worker attachment download from Telegram Bot API
- local save to shared `/storage`
- text extraction for `txt`, `pdf`, `docx`
- executor input composition with truncation guardrails
- AI execution through configured executor
- Telegram result delivery with persisted delivery diagnostics

## Final E2E checklist
1. Start the normal stack:
```bash
make up
make ps
```
2. Confirm `bot`, `backend`, `worker`, `postgres`, `redis` are running.
3. Send a Telegram document with an analysis instruction.
4. Confirm bot acknowledgement returns a task id.
5. Confirm `GET /tasks/{task_id}` shows:
   - `status=done`
   - attachment present
   - `download_status=downloaded`
   - non-empty `local_path`
   - non-empty `result_text`
   - `delivery_status=delivered`
6. Confirm Telegram receives the final worker reply.

## Remaining risks
- live Telegram E2E must still be validated against the real deployed token/chat after environment changes
- concurrent normal worker plus manual debug worker can make tests nondeterministic
- no dedicated healthcheck proves worker can consume queue end-to-end
- observability is log/API based; there is no compact operator dashboard yet
- unsupported MIME types still fail the task instead of partial success

## Next technical tasks
- add a lightweight worker health/readiness signal tied to queue consumption
- add one-line structured completion logs for `task_id`, final status, and delivery status
- add a deterministic E2E smoke path for document processing with a controllable Telegram test fixture
- improve failure categorization for attachment download, extraction, execution, and delivery
