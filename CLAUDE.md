# CLAUDE.md

## Project
AI Assistant Platform is a Telegram-first task execution system evolving toward a reliable multi-agent execution pipeline.

Primary flow:
`Telegram -> Bot -> Backend -> PostgreSQL -> Redis queue -> Worker -> AI executor -> Telegram delivery`

## Stack
- Python
- FastAPI
- aiogram
- PostgreSQL
- Redis
- Docker Compose

## Key Paths
- `backend/` API, queue, execution pipeline, worker runtime support
- `bot/` Telegram bot entrypoints
- `worker/` worker-stage code and future expansion area
- `infra/` Compose files and runtime infrastructure
- `docs/` source of truth for architecture and operations
- `scripts/` smoke helpers
- `ops-control/ACTIVE_OWNER.md` live server ownership ledger

## Standard Commands
- `make up`
- `make ps`
- `make smoke`
- `make smoke-worker`

Use smoke checks after backend/queue/worker changes. Do not rebuild or restart unrelated services without explicit need.

## Shared Server Rules
- This repo runs on a low-memory shared server.
- Assume swap/RAM pressure is a standing risk until the server is upgraded.
- Do not start or keep a heavy live Remote SSH/IDE session unless you are the active live operator.
- Respect the rule: one active live operator on the server at one time.
- Prefer off-server work via git diff, docs, logs, snapshots, and user-provided artifacts whenever possible.

## Safe Working Rules
- Keep changes minimal, reversible, and documented.
- Do not modify `infra/docker-compose.yml` without an explicit task.
- Do not touch `.env`, tokens, or credentials unless explicitly requested.
- Do not run destructive actions, force resets, service restarts, or irreversible migrations without confirmation.
- Minimize watcher and extension load if you are working through Remote SSH.

## Handoff Protocol
- Read `AGENTS.md`, `docs/ai_assistant_memory.md`, `docs/AI_AGENT_WORKFLOW.md`, and `docs/SERVER_RUNBOOK.md` before substantial work.
- Before live work, check `ops-control/ACTIVE_OWNER.md`.
- When handing off, leave:
  - goal and scope
  - files changed
  - commands run
  - risks/open questions
  - whether live access is still required

## When Claude Should Work Live
- Direct code edits in this repo
- Local smoke verification
- Runtime diagnosis that requires on-host inspection

## When Claude Should Stay Off-Server
- Reviewing diffs
- Drafting plans or architecture
- Summarizing logs already captured by another operator
- Preparing implementation notes for the next live operator
