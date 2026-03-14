# AI Assistant --- Project Context for AI Agents

## Purpose

This project builds an **AI Assistant platform** that starts with
practical user-testable workflows and evolves into a platform of
specialized agents and agent teams.

The current validated business scenario is:

> Upload a client document → AI analyzes it → returns a concise summary
> of problems.

The current `Document Analysis Agent` is the first production-tested
agent, not the final form of the system.

------------------------------------------------------------------------

## Current Architecture

    Telegram
       │
       ▼
    Bot (Telegram API)
       │
       ▼
    Backend (FastAPI)
       │
       ├── PostgreSQL (tasks database)
       └── Redis (task queue)
                │
                ▼
             Worker
                │
                ▼
          Agent Execution
                │
                ▼
         Telegram delivery

Normal runtime mode:

    ai_worker (compose service)

Debug/fallback mode:

    manual worker inside ai_backend for diagnostics only

------------------------------------------------------------------------

## Key Components

### Bot

Container: `ai_bot`

Responsibilities: - Receive Telegram messages - Accept documents -
Create tasks via backend API

Supported commands:

    /start
    /help
    /health
    /task

Also supports **plain text input without commands**.

------------------------------------------------------------------------

### Backend

Container: `ai_backend`

Framework: **FastAPI**

Endpoints:

    POST /tasks
    GET  /tasks/{id}

Responsibilities: - Store tasks in PostgreSQL - Push task IDs into Redis
queue - Return task_id to bot

------------------------------------------------------------------------

### Queue

Technology: **Redis**

Queue key:

    tasks:queue

Payload:

    task_id

------------------------------------------------------------------------

### Worker

Processes tasks from Redis.

Task lifecycle:

    created → queued → processing → done | failed

Worker steps: 1. read task_id from Redis 2. load task from PostgreSQL 3.
download attachments (Telegram) 4. extract text from files 5. compose
execution input 6. send request to agent executor 7. deliver result to
Telegram

------------------------------------------------------------------------

## Current MVP Scope

The current MVP includes:

- Telegram task intake
- document upload from Telegram
- attachment download and text extraction
- task persistence in PostgreSQL
- Redis queue handoff
- dedicated `ai_worker` runtime
- AI execution through provider-aware executor layer
- Telegram result delivery
- task-level observability logs
- separated smoke flows for normal mode and debug mode

Confirmed by the user through Telegram:

    Telegram document → attachment download → text extraction
    → AI analysis → Telegram reply

------------------------------------------------------------------------

## Target Platform Model

The long-term target is not a single-use assistant, but a platform with:

- specialized agents
- agent teams
- orchestration layer
- approval-oriented workflows

The current `Document Analysis Agent` is the first validated example of
this model.

------------------------------------------------------------------------

## Core Platform Entities

### Agent

A specialized execution unit with a defined role, execution boundaries,
and expected result contract.

### Agent Capability

A concrete capability exposed by an agent, such as document analysis,
fact-checking, drafting, routing, or tool invocation.

### Agent Team

A coordinated set of agents that handles one business scenario through
routing and handoff rules.

### Task

A work item submitted by a user or another system and tracked through
execution lifecycle.

### Task Routing

The decision layer that selects the correct agent or agent team for a
given task.

### Agent Result Contract

A normalized result shape that allows safe handoff between agents and
system layers.

### Approval Step

A controlled checkpoint where a human or policy gate approves, edits, or
rejects work before continuation.

------------------------------------------------------------------------

## Current Status

The current end-to-end pipeline works:

    Telegram → Bot → Backend → Redis → Worker → OpenAI → Telegram reply

Working features: - text task processing - document upload - attachment
extraction pipeline - OpenAI integration - Telegram result delivery -
smoke tests

Current positioning:

- Document Analysis Agent is the first production-tested agent
- current Telegram flow is the first validated agent workflow
- the system is now ready to evolve into agent registry, contracts, and
  agent-team architecture

------------------------------------------------------------------------

## Next Engineering Priorities

1.  Build architecture foundations for specialized agents and agent
    teams.
2.  Define routing, result contract, and approval-oriented workflow
    primitives.
3.  Keep the current Document Analysis Agent stable as the first
    validated agent.
4.  Explore email-driven multi-agent workflow as a likely next business
    scenario.

------------------------------------------------------------------------

## MVP Completion Status

System readiness:

- core Telegram document analysis agent is production-tested
- normal runtime mode is compose-based
- debug/fallback mode remains available for diagnostics
- current MVP pipeline should remain stable while platform abstractions
  are introduced in future stages
