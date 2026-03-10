# Task Execution System - Step 3 (Minimal Worker Lifecycle)

## Goal
Add a minimal worker that consumes `task_id` from Redis queue and advances task lifecycle in PostgreSQL:

`queued -> processing -> done / failed`

## What changed
- Added worker runtime loop in backend codebase (`app.worker_runtime`) for maximum reuse of existing DB/models/queue modules.
- Added worker entrypoint in `worker/app/main.py` as a thin wrapper.
- Added smoke test for worker lifecycle (`make smoke-worker`).

## Worker behavior
1. `BLPOP` from Redis queue (`tasks:queue` by default).
2. Load task by `task_id` from PostgreSQL.
3. If task exists and status is `queued`:
   - update to `processing`
   - run MVP-safe mock execution (small delay)
   - update to `done`
4. If task status is still `created` (race with enqueue/update):
   - requeue `task_id`
   - continue safely
5. On processing error:
   - update status to `failed`
6. If task is missing or status is not `queued`:
   - log warning/info
   - continue loop without crashing

## Logging
Worker logs include:
- task picked
- processing started
- processing completed
- processing failed

## Normal operation mode
Run the system with dedicated services, including `ai_worker`:
```bash
docker compose -f infra/docker-compose.yml up -d --build
```

Expected service roles:
- `ai_backend` serves API traffic only.
- `ai_worker` is the штатный worker process for queue consumption and task execution.

Notes:
- `worker` uses the same backend image and the same `env_file` as `backend`.
- `worker` depends on `postgres` and `redis`.
- `backend` and `worker` share `/storage` through a named volume so attachment files written under `STORAGE_INPUT_DIR=/storage/input` remain consistent across both containers.

## Debug / fallback mode
Run worker manually inside the backend container only for diagnostics or emergency fallback:
```bash
docker exec -it ai_backend python -m app.worker_runtime
```

Important:
- `ai_backend` must receive the same runtime env needed by worker modules, including `TELEGRAM_BOT_TOKEN`.
- In the current MVP this is provided through `infra/docker-compose.yml` via `env_file` on the `backend` service.

One-shot mode (for diagnostics):
```bash
docker exec -it ai_backend python -m app.worker_runtime --max-tasks 1
```

Manual `docker exec ... python -m app.worker_runtime` remains available for diagnostics.

## Smoke-check
Run:
```bash
make smoke-worker
```

Smoke worker flow:
- create task via API
- expect the normal `ai_worker` service to consume the queue
- wait until task status becomes `done`
- fail with non-zero exit if status becomes `failed` or timeout is reached

Provider override smokes intentionally use debug mode so they can inject temporary env overrides:
```bash
make smoke-worker-openai-no-key
make smoke-worker-openai
```
