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

## Manual run (without docker-compose changes)
Run worker inside current backend container:
```bash
docker exec -it ai_backend python -m app.worker_runtime
```

One-shot mode (for diagnostics):
```bash
docker exec -it ai_backend python -m app.worker_runtime --max-tasks 1
```

## Smoke-check
Run:
```bash
make smoke-worker
```

Smoke worker flow:
- create task via API
- run worker runtime
- wait until task status becomes `done`
- fail with non-zero exit if status becomes `failed` or timeout is reached
