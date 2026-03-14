# AI Assistant Memory

## Project mission
Build a reliable AI Assistant platform that starts from practical Telegram-first workflows, validates specialized agents in real use, and evolves into a platform of agents and agent teams.

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
- approval items as first-class platform entities

The core MVP document analysis flow has been confirmed by the user through Telegram:

`Telegram document -> attachment download -> text extraction -> AI analysis -> Telegram reply`

The current `Document Analysis Agent` is the first production-tested agent, not the final form of the system.

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
- approval items are stored in PostgreSQL and managed through backend API

Long-term target direction:
- specialized agents
- agent teams
- orchestration layer
- approval-oriented workflows

## Platform entities
- `Agent`
  A specialized execution unit with a defined role, inputs, outputs, and operational constraints.
- `Agent Capability`
  A concrete thing an agent can do, such as document analysis, routing, drafting, fact-checking, or delivery preparation.
- `Agent Team`
  A coordinated set of agents that work on one business scenario through routing and handoff rules.
- `Task`
  A user or system work item that moves through intake, routing, execution, approval, and delivery.
- `Task Routing`
  The decision layer that selects the right agent or agent team for a given task.
- `Agent Result Contract`
  A normalized result shape that lets agents hand work off safely and predictably.
- `Approval Step`
  A controlled checkpoint where a human or policy gate approves, edits, or rejects a result before the next step.

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
- Document Analysis Agent validated as the first production-tested agent
- approval item entity and approval API foundation added for future workflows

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
- strengthen architecture foundations for specialized agents and agent teams
- define platform-level contracts for routing, results, and approvals
- explore email-driven multi-agent workflow as a likely next business scenario
- keep operator-facing observability and smoke flows practical for the current MVP

## Rules for Codex
- treat repo docs as the primary context
- prefer `docs/ai_assistant_memory.md` as the first-stop working summary
- use `ai_worker` as the default worker assumption
- treat manual worker launch inside `ai_backend` as debug/fallback only
- treat the Document Analysis Agent as the first validated agent, not the whole product vision
- align new design decisions with specialized agents, agent teams, orchestration, and approval workflows
- preserve current MVP behavior unless the task explicitly asks for change
- keep docs updated when operational behavior changes
- do not treat old versioned context files as source of truth
