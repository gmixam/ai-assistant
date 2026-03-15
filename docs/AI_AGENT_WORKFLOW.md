# AI Agent Workflow

## Purpose
This document defines the safe operating model for running multiple AI-assisted projects on one constrained server before the host is upgraded.

The current server has limited RAM and previously experienced real OOM events that killed `node` processes used by `vscode-server` and related extension hosts. Because of that, the default operating mode must be resource-aware and conservative.

## Environment Assumption
- One server hosts multiple independent projects.
- Different projects may be led by different AI agents.
- The server is stable enough for runtime workloads and controlled development work, but not for unrestricted parallel live IDE usage.
- Stability takes priority over maximum parallelism.

## Core Rule
Only one active live operator may use the server at a time.

`live operator` means the person or AI session currently allowed to use Remote SSH, open an IDE against the host, run local diagnostics, edit files directly on the server, or perform smoke checks on-host.

All other agents must work off-server through:
- git commits and diffs
- repository docs
- exported logs
- snapshots and command output
- issue/task descriptions
- review comments and handoff notes

## Role Model
- `Claude Code`
  Primary implementer for its assigned repository or task stream.
- `Codex`
  Primary implementer for its assigned repository or task stream.
- `Gemini`
  Use as either:
  - primary implementer for a separate new project, or
  - analyst, reviewer, or architecture support agent

These roles may exist in parallel across projects, but live server access is serialized.

## Operating Modes
### Mode 1: Live Operator
Use only when required for:
- direct code changes on the server
- local smoke runs
- runtime inspection
- log capture that cannot be delegated through stored artifacts

Requirements:
- claim ownership in `ops-control/ACTIVE_OWNER.md`
- keep only one Remote SSH IDE session open
- keep only required extensions enabled on the remote host
- avoid parallel AI chat/code assistants on the same remote session
- close the session after the task or handoff is complete

### Mode 2: Off-Server Contributor
Use by default for:
- planning
- code review
- architecture review
- diff review
- documentation work
- interpreting logs and diagnostics already captured by the live operator

Inputs for off-server work:
- branch or commit reference
- patch/diff
- command output
- file snapshots
- screenshots if needed

## Conflict Prevention
- Do not let two AI agents operate live against the same server simultaneously.
- Do not let two agents independently edit the same live branch without a handoff.
- Prefer one task owner per branch.
- Record handoffs in docs or task notes, not only in chat history.
- If two agents must contribute to one project, use a primary executor and a reviewer pattern.

## Handoff Contract
Every handoff should include:
- current objective
- current branch or commit SHA
- files touched
- validations already run
- validations still needed
- runtime assumptions
- whether live server access is still needed
- known risks and rollback notes

Recommended artifact set:
- `git diff` or commit link
- relevant log excerpts
- exact commands run
- updated docs if behavior changed

## Resource-Aware Rules
- Assume the server remains memory-constrained until explicitly upgraded.
- Do not keep multiple heavy remote AI sessions open in parallel.
- Do not keep multiple VS Code windows connected to the same host unless absolutely necessary.
- Disable remote extensions that are not required for the active task.
- Minimize file watchers and background language servers.
- Prefer CLI tools and focused editing over full IDE usage when possible.

## Practical Assignment Model
- Project A
  Claude Code is the primary executor.
- Project B
  Codex is the primary executor.
- Project C
  Gemini may act as primary executor, or as an analyst/reviewer supporting Claude Code or Codex.

Allowed:
- one project live on the server
- other projects progressing through off-server planning, review, or patch preparation

Not allowed on the current server profile:
- several live Remote SSH AI sessions at once
- several heavy extension hosts on the same host at once
- uncontrolled multi-agent live editing on one runtime host

## Upgrade Trigger
Revisit this workflow when any of the following becomes true:
- RAM is increased and swap is configured
- multiple developers need simultaneous live IDE access as a normal mode
- multiple active projects require local integration testing at the same time
- OOM or SSH instability recurs despite following this workflow
