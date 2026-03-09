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
