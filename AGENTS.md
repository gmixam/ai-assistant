# AGENTS.md

## Project Purpose
AI Assistant Platform is a Telegram-first task execution platform.
Current objective is to evolve from MVP task intake to a reliable Task Execution System, then to an AI execution pipeline.

## Environment
- Host: Hetzner VPS
- OS: Ubuntu 24.04
- Runtime: Docker Compose
- Repository root: `/root/ai-assistant`
- Current resource mode: constrained shared server until RAM/swap upgrade

## Shared Server Operating Mode
- This repository lives on a shared low-memory server that also hosts other projects.
- Treat the server as a constrained runtime/dev host, not an unlimited multi-user workstation.
- Only one active live operator may use server-side AI/IDE tooling at a time.
- Default mode for all other agents is off-server work through git diffs, docs, logs, snapshots, and user-provided artifacts.
- Avoid concurrent heavy Remote SSH sessions, multiple VS Code extension hosts, or multiple live AI coding sessions on the same host.

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
- Default to off-server reasoning when live server access is not required.
- Before starting live work on the server, check `ops-control/ACTIVE_OWNER.md` and respect the single live-operator rule.
- Keep remote IDE load small: minimal extensions, minimal watchers, minimal parallel terminals.
- Use handoff artifacts rather than second live sessions when another agent needs context.

## Agent Roles
- `Codex`
  Primary implementation agent for this repository unless the user assigns otherwise.
- `Claude Code`
  May operate as primary implementer for another repository on the same server or as a collaborator for planning, refactoring strategy, and handoff review.
- `Gemini`
  Use as a new-project contributor, reviewer, or architecture analyst unless explicitly assigned as the primary operator for a separate project.
- Multiple agents may work in parallel across projects, but only one may hold live server operator status at a time.

## Live Access And Handoffs
- Live access is allowed only for tasks that need direct repository edits, container/runtime inspection, or local smoke verification.
- Off-server work is preferred for review, analysis, planning, spec drafting, diff review, and log interpretation.
- Handoffs should include:
  - current goal and branch/commit
  - touched files
  - open risks
  - exact commands run
  - pending validations
- Record current live ownership and next handoff target in `ops-control/ACTIVE_OWNER.md` whenever server operator responsibility changes.

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

## Safe Git Workflow (Mandatory)
After completing each implementation step, OpenClaw/Codex must:
1. Run relevant smoke checks for changed scope.
2. Run `git status`.
3. Verify there are no secrets or transient artifacts in tracked changes (`.env`, tokens, local storage inputs, logs, smoke temp files, local state dirs).
4. If any new environment variable was introduced, update `.env.example` in the same step.
5. Then execute:
   - `git add .`
   - `git commit -m "<clear scope message>"`
   - `git push`

This file is the default system context for OpenClaw in this repository.
