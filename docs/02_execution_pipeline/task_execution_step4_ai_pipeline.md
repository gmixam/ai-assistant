# Task Execution System - Step 4 (AI Execution Pipeline Abstraction)

## Goal
Prepare worker execution architecture so mock execution can be replaced by real AI executors without rewriting worker loop.

## Execution contract
Worker now relies on a stable executor contract:
- `TaskExecutor.execute(task) -> ExecutionResult`
- `ExecutionResult` contains:
  - `success: bool`
  - `result_text: str | None`
  - `error_text: str | None`

Default implementation:
- `MockExecutor` (used when `TASK_EXECUTOR=mock`, default)

Executor selection:
- `build_executor()` in `backend/app/executors/factory.py`

## Worker flow with abstraction
Worker lifecycle remains:
`queued -> processing -> done / failed`

Processing logic:
1. Pick `task_id` from Redis.
2. Load task from PostgreSQL.
3. Set `processing`.
4. Call executor contract.
5. Persist:
   - success: `status=done`, write `result_text`, clear `error_text`
   - failure: `status=failed`, write `error_text`, clear `result_text`

## Task model extension (non-destructive)
Task now includes nullable fields:
- `result_text`
- `error_text`

Schema bootstrap is MVP-safe:
- `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for existing DBs.

## Smoke test updates
`make smoke-worker` now validates:
- task reaches `done`
- `result_text` is present

## How to add real AI executors next
1. Add a new executor class implementing `TaskExecutor`:
   - examples: `KimiExecutor`, `DeepSeekExecutor`, `OpenAIExecutor`
2. Register it in `executors/factory.py` via `TASK_EXECUTOR`.
3. Keep worker loop unchanged.
4. Add provider-specific error mapping to `ExecutionResult(error_text=...)`.
