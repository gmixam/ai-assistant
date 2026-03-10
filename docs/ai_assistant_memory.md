# AI Assistant Memory

## Project mission
Build a reliable Telegram-first AI Assistant platform that accepts user tasks, executes them through a controlled worker pipeline, and returns useful results back to Telegram.

## Current MVP scope
- Telegram task intake through bot
- backend task creation and persistence
- Redis queue handoff
- dedicated compose worker runtime
- Telegram document attachment download
- text extraction for `txt`, `pdf`, `docx`
- AI analysis execution
- Telegram result delivery
- smoke checks for normal mode and debug mode

The core MVP document analysis flow has been confirmed by the user through Telegram:

`Telegram document -> attachment download -> text extraction -> AI analysis -> Telegram reply`

## Current architecture
Primary flow:

`Telegram -> Bot -> Backend -> PostgreSQL -> Redis queue -> Worker -> AI executor -> Telegram delivery`

Runtime services:
- `ai_bot`
- `ai_backend`
- `ai_worker`
- `ai_postgres`
- `ai_redis`

Operational details:
- normal runtime mode: `ai_worker` as Docker Compose service
- debug/fallback mode: manual worker inside `ai_backend` for diagnostics only
- `ai_backend` and `ai_worker` share `/storage`
- task-level observability logs exist in queue, worker, attachment, execution, and delivery stages

## Operational truth
- repo documentation is the source of truth
- the standard worker runtime is `ai_worker`, not manual `docker exec`
- manual worker launch is diagnostic only and should not be treated as normal operation
- normal and debug smoke modes are intentionally separated
- shared `/storage` is required for consistent attachment handling between backend and worker

## Constraints
- keep MVP-safe changes first
- avoid breaking bot/backend API contracts unless explicitly requested
- do not change queue architecture casually
- do not introduce heavy observability infrastructure at this stage
- do not remove fallback diagnostics unless a safe replacement exists
- prefer minimal, reversible changes

## Completed milestones
- PostgreSQL task persistence
- Redis queue integration
- worker runtime and lifecycle
- provider-aware execution layer
- OpenAI provider path
- Telegram metadata persistence
- Telegram delivery from worker
- Telegram attachment download and text extraction
- dedicated `ai_worker` compose service
- shared storage between backend and worker
- task-level observability logs
- separated smoke modes for normal/debug operation
- MVP document analysis pipeline confirmed through Telegram

## Current main documents
- `docs/README.md`
- `docs/00_overview/ai_assistant_project_context.md`
- `docs/00_overview/ai_assistant_architecture.md`
- `docs/00_overview/ai_assistant_system_design.md`
- `docs/01_mvp/mvp_document_analysis_readiness.md`
- `docs/02_execution_pipeline/task_execution_step7_telegram_e2e.md`
- `docs/02_execution_pipeline/task_execution_step8_file_reading_mvp.md`
- `docs/03_operations/smoke_tests.md`

## Next priorities
- improve operator-facing observability without changing architecture
- keep smoke flows reproducible in compose-based operation
- strengthen worker readiness and diagnostics
- prepare the next stage of execution reliability and future architecture evolution

## Rules for Codex
- treat repo docs as the primary context
- prefer `docs/ai_assistant_memory.md` as the first-stop working summary
- use `ai_worker` as the default worker assumption
- treat manual worker launch inside `ai_backend` as debug/fallback only
- preserve current MVP behavior unless the task explicitly asks for change
- keep docs updated when operational behavior changes
- do not treat old versioned context files as source of truth
