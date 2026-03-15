# Docs Structure

Repository docs are the source of truth for project context and operations.

## Primary documents
- `docs/ai_assistant_memory.md`
  Working memory and current operational truth for the project.
- `docs/AI_AGENT_WORKFLOW.md`
  Multi-agent operating model for shared-server work.
- `docs/SERVER_RUNBOOK.md`
  Shared-server safety and live-access runbook.
- `docs/00_overview/ai_assistant_project_context.md`
  Project context and current stage summary.
- `docs/00_overview/ai_assistant_architecture.md`
  High-level architecture reference.
- `docs/00_overview/ai_assistant_system_design.md`
  Broader system design direction.
- `docs/01_mvp/mvp_document_analysis_readiness.md`
  Current MVP readiness and scope.
- `docs/03_operations/smoke_tests.md`
  Operational smoke/runbook reference.

## Structure
- `00_overview/`
  Core context, architecture, and system design references.
- `01_mvp/`
  Current MVP readiness and scope documents.
- `02_execution_pipeline/`
  Step-by-step execution pipeline implementation notes.
- `03_operations/`
  Operational runbooks, smoke checks, and diagnostics.
- `04_future_architecture/`
  Reserved for next-stage architecture documents.

## Documentation rules
- repo docs are the source of truth
- `docs/ai_assistant_memory.md` is the primary working summary for current state
- `docs/AI_AGENT_WORKFLOW.md` and `docs/SERVER_RUNBOOK.md` define shared-server operating constraints
- operational behavior should be documented here before relying on external notes or chat history
- versioned context files are not source of truth
- if archived/versioned context files exist in the future, treat them as historical reference only
