# Task Execution System - Step 2 (Redis Enqueue)

## Goal
After creating a task in PostgreSQL, backend enqueues task transport data for async processing.

## What changed
- Added Redis queue integration in backend.
- `POST /tasks` now performs:
  1. Create task in PostgreSQL with status `created`.
  2. Enqueue `task_id` into Redis list queue.
  3. Update task status in PostgreSQL to `queued`.
- `POST /tasks` request/response format remains bot-compatible.

## Queue contract (MVP)
- Transport: Redis List (`RPUSH`/`BLPOP` compatible).
- Queue name: `tasks:queue` (configurable via `TASK_QUEUE_NAME`).
- Payload: only `task_id` (string UUID).

This keeps Redis as transport only; PostgreSQL remains source of truth.

## Failure behavior (enqueue error)
- Backend does not crash with unhandled exception.
- Returns controlled `503` with message and `task_id`.
- Task remains persisted in PostgreSQL with status `created`.

Why this behavior:
- Avoids silent data loss.
- Preserves recoverability and manual/automatic requeue options.
- Keeps state explicit and auditable.

## Manual verification
1. Create a task:
```bash
curl -s -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"input_text":"Queue integration test"}'
```

2. Check task in PostgreSQL:
```bash
curl -s http://localhost:8000/tasks/<task_id>
```
Expected status: `queued` (when Redis is healthy).

3. Check Redis queue length:
```bash
docker exec -it ai_redis redis-cli LLEN tasks:queue
```

4. Inspect queue payload:
```bash
docker exec -it ai_redis redis-cli LRANGE tasks:queue 0 -1
```
Expected payload entries: task UUIDs.
