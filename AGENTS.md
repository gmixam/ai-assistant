# AGENTS.md

## Project Purpose
AI Assistant Platform is a Telegram-first task execution platform.
Current objective is to evolve from MVP task intake to a reliable Task Execution System, then to an AI execution pipeline.

## Environment
- Host: Hetzner VPS
- OS: Ubuntu 24.04
- Runtime: Docker Compose
- Repository root: `/root/ai-assistant`

## Current Architecture
Primary flow:
`Telegram -> Bot (aiogram) -> Backend (FastAPI) -> PostgreSQL/Redis`

Current state in code:
- Bot receives `/task <text>` and sends `POST /tasks` to backend.
- Backend exposes `/health` and `/tasks`.
- Task creation currently stores data in memory (MVP behavior).

## Services
Current runtime services (Docker Compose):
- `bot` (Telegram bot, aiogram)
- `backend` (FastAPI API)
- `postgres` (PostgreSQL)
- `redis` (Redis)

Repository directories:
- `bot/`
- `backend/`
- `worker/` (prepared for next stages)
- `infra/` (contains docker-compose)
- `storage/`
- `docs/`

## Implemented (MVP Infrastructure Completed)
- Telegram bot is running and accepts commands.
- `/task` command is integrated with backend.
- Backend endpoint `POST /tasks` creates a task object and returns task id.
- Base infrastructure with PostgreSQL and Redis exists in Compose.

## Next Stage (Task Execution System)
Priority workstreams:
- Task storage in PostgreSQL (replace in-memory task storage).
- Redis queue integration for async task processing.
- Worker service implementation for task consumption/execution.
- AI execution pipeline foundations (task lifecycle, statuses, result persistence).

## Agent Working Rules
When making changes, OpenClaw must:
- Keep changes minimal, reversible, and aligned with current architecture.
- Prefer MVP-safe implementation first; avoid overengineering.
- Preserve API compatibility for existing bot/backend interaction unless task explicitly requests breaking changes.
- Update docs together with code when behavior/architecture changes.
- Propose plan and impact before large refactors.
- Add or update tests for non-trivial backend/worker logic.
- After changes in `backend`, queue integration, or `worker`, run smoke-check before final handoff (`make smoke`; for worker lifecycle changes also run `make smoke-worker`).

## Safety and Change Guardrails
Strict rules:
- Do not change `infra/docker-compose.yml` without an explicit user task.
- Do not remove existing services.
- Do not modify production secrets or secret values (`.env`, tokens, credentials) unless explicitly requested.
- Do not run destructive migrations (drop/truncate/irreversible schema changes).
- Any new service must be proposed and implemented first as MVP-safe.
- Before changing `backend` or `bot`, explicitly verify consistency with flow:
  `Telegram -> Bot -> Backend -> PostgreSQL/Redis`.

## Operational Prohibitions
Without explicit approval, OpenClaw must not:
- Execute destructive commands (`rm -rf`, `git reset --hard`, force drops).
- Rewrite history or delete branches/tags.
- Introduce runtime-coupled changes outside task scope.
- Change host-level system configuration unrelated to repository tasks.

## Preferred Delivery Pattern For Next Iterations
For Task Execution and AI pipeline tasks:
1. Design minimal schema/queue contract.
2. Implement backend persistence and enqueue.
3. Implement worker consume/process/update status.
4. Add observability (`/health`, logs, basic metrics hooks).
5. Document runbook and rollback notes.

## QA Workflow (OpenClaw/Codex)
For backend/queue/worker changes:
1. Rebuild/restart only the needed service if required.
2. Run `make smoke`.
3. For worker lifecycle changes, run `make smoke-worker`.
4. Report PASS/FAIL with a short summary and failed step (if any).

This file is the default system context for OpenClaw in this repository.
