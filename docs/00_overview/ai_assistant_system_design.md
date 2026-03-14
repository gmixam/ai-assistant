# AI Assistant Platform — System Design

## Purpose

This document describes the target system design of **AI Assistant Platform** as it evolves from an MVP task intake system into a **platform of specialized agents and agent teams**.

It complements the project context documents and the architecture overview.

---

## 1. Design Goals

The system is designed to:

- accept real work tasks from a user
- orchestrate task execution through backend services
- process tasks asynchronously
- support multiple AI workers and AI providers
- support specialized agents and agent teams
- evolve into an orchestration-driven, approval-aware architecture
- remain simple enough for MVP delivery, but scalable enough for future SaaS expansion

---

## 2. Current Design State

At the current stage, the system already supports:

- Telegram bot as the user interface
- FastAPI backend
- task creation via `/task`
- Docker-based deployment on a Hetzner VPS
- Redis and PostgreSQL as infrastructure components

Current working flow:

```text
User
↓
Telegram Bot
↓
Backend API
↓
Task created
```

This is the first working integration milestone and serves as the base for the execution layer.

The current `Document Analysis Agent` is the first production-tested agent on top of this platform direction.

---

## 3. Target Execution Model

The target model separates the system into distinct responsibilities:

```text
User Interface
↓
Task Intake
↓
Task Persistence
↓
Task Queue
↓
Task Execution
↓
Task Routing / Orchestration
↓
Result Storage
↓
Result Delivery
```

This separation ensures:

- low coupling between services
- asynchronous execution
- scalability of workers
- flexibility in AI orchestration
- future compatibility with agent teams and approval workflows

---

## 4. Core System Layers

## 4.1 User Interface Layer

Primary interface:

- Telegram Bot

Future interfaces:

- Web dashboard
- API integrations
- Enterprise workflow connectors

Responsibilities:

- receive task requests
- accept files and instructions
- notify user about status
- deliver results back to user

---

## 4.2 Task Intake Layer

Current implementation:

- Bot command `/task`
- Backend endpoint `POST /tasks`

Responsibilities:

- validate incoming request
- normalize payload
- generate task identifier
- initiate task lifecycle

Input example:

```json
{
  "input_text": "Проанализируй материалы клиента и предложи решения"
}
```

---

## 4.3 Persistence Layer

Primary storage:

- PostgreSQL

Main entities planned:

- users
- tasks
- task_steps
- uploaded_files
- artifacts
- execution_logs

Tasks should eventually include fields such as:

| field | purpose |
|---|---|
| id | unique identifier |
| user_id | owner of the task |
| input_text | task text |
| status | lifecycle status |
| created_at | creation timestamp |
| started_at | execution start |
| finished_at | execution finish |
| result_json | structured result |
| error_message | failure reason |

This layer is the source of truth for the platform.

---

## 4.4 Queue Layer

Queue technology:

- Redis

Planned queue:

```text
tasks_queue
```

Responsibilities:

- decouple API from task execution
- allow background processing
- support multiple workers
- enable retries and delayed execution in future

At the MVP stage, queue messages may contain:

- `task_id`

Later they may also include:

- task type
- priority
- execution profile
- retry metadata

---

## 4.5 Execution Layer

Execution service:

- Worker

Responsibilities:

- read task identifiers from queue
- load task from PostgreSQL
- change task status
- launch AI processing pipeline
- save outputs and status back to database

Target lifecycle:

```text
created
↓
queued
↓
running
↓
done / failed
```

---

## 4.6 AI Orchestration Layer

This is the core intelligence layer of the platform.

It will initially begin as:

- a single worker pipeline
- one execution strategy
- one or several LLM providers

Later it evolves into:

- orchestration-based routing
- multiple specialized agents
- agent teams
- tool-aware execution
- approval-oriented workflows
- agent collaboration

### Core platform entities

- `Agent`
  A specialized execution unit with a defined role and result contract.
- `Agent Capability`
  A concrete capability exposed by an agent.
- `Agent Team`
  A coordinated execution group for one business scenario.
- `Task`
  A unit of work routed into the platform.
- `Task Routing`
  The selection and dispatch logic for agents and agent teams.
- `Agent Result Contract`
  A normalized result format that supports safe handoffs.
- `Approval Step`
  A checkpoint that requires human or policy approval before continuation.

---

## 5. MVP Execution Pipeline

The near-term target pipeline is:

```text
Telegram
↓
Bot
↓
Backend
↓
PostgreSQL
↓
Redis Queue
↓
Worker
↓
AI Processing
↓
Result saved
↓
Result returned to user
```

### Step-by-step sequence

1. User sends `/task <text>` in Telegram
2. Bot calls backend `POST /tasks`
3. Backend creates task in database
4. Backend pushes `task_id` to Redis queue
5. Worker consumes `task_id`
6. Worker loads task payload
7. Worker runs AI execution logic
8. Worker stores result
9. Bot or backend later returns result/status to user

This is the first real **task execution system** milestone and the first validated agent runtime path.

Current validated agent:
- Document Analysis Agent

---

## 6. Planned Multi-Agent Design

The long-term design introduces an **orchestration layer** that coordinates specialized agents, agent teams, and approval steps.

### High-level model

```text
Orchestration Layer
↓
├── Document Analysis Agent
├── Analyst Agent
├── Research Agent
├── Writer Agent
├── Tool Agent
└── Approval Step
```

---

## 6.1 Orchestration Layer

Role:

- central orchestrator of the AI system

Responsibilities:

- interpret the user request
- determine execution strategy
- split work into subtasks
- assign subtasks to specialized agents
- route work into agent teams when needed
- combine and validate results
- manage retries or fallback flows
- control approval-oriented transitions

The orchestration layer is not intended to do all work itself.  
Its purpose is routing, coordination and quality control.

---

## 6.2 Analyst Agent

Responsibilities:

- analyze problem statements
- identify issues and patterns
- structure findings
- build problem tables
- cluster and prioritize insights

Typical use cases:

- client issue analysis
- requirements decomposition
- problem extraction from documents
- business analysis support

This aligns directly with the original MVP vision of the Business Analyst Agent. fileciteturn1file0

---

## 6.3 Research Agent

Responsibilities:

- gather relevant supporting information
- verify facts
- enrich context
- compare alternatives
- support recommendation quality

Typical use cases:

- finding reference data
- gathering regulations or external facts
- validating assumptions
- adding context to analysis

---

## 6.4 Writer Agent

Responsibilities:

- synthesize outputs into clear deliverables
- generate reports
- prepare summaries
- convert structured outputs into user-facing documents

Typical use cases:

- report generation
- summary generation
- action plans
- client-ready outputs

---

## 6.5 Tool Agent

Responsibilities:

- invoke external tools and services
- handle documents, files, APIs, and integrations
- bridge LLM logic with operational systems

Future tool categories may include:

- file parsers
- spreadsheet tools
- document generation
- email/calendar tools
- web search
- CRM/BI/Jira integrations

---

## 7. Evolution Path

## Stage 1 — MVP Infrastructure

Completed:

- Telegram bot
- FastAPI backend
- Docker-based deployment
- Redis and PostgreSQL infrastructure
- `/task` integration between bot and backend

This matches the documented transition from infrastructure to task system work. fileciteturn1file1 fileciteturn1file2

---

## Stage 2 — Task Execution System

Completed foundation:

- persist tasks in PostgreSQL
- enqueue tasks in Redis
- add worker service
- process task lifecycle statuses
- Telegram delivery from worker
- attachment download and extraction

This stage is materially in place and powers the first validated agent.

---

## Stage 3 — AI Execution

Current capability layer:

- connect one or more LLM providers
- generate structured results
- store outputs
- return final deliverables to user

Initial providers considered in project context:

- OpenAI
- DeepSeek
- Kimi fileciteturn1file1 fileciteturn1file2

---

## Stage 4 — Agent Platform Foundation

Advanced architecture:

- orchestration layer
- specialized role agents
- agent teams
- multi-step orchestration
- approval-oriented workflows
- agent collaboration
- tool usage

Likely next business scenario:

- email-driven multi-agent workflow

---

## Stage 5 — Scalable Platform

Future platform capabilities:

- multiple users / SaaS model
- tenant isolation
- billing / subscriptions
- monitoring
- retries and fault tolerance
- audit logs
- admin dashboard

---

## 8. Task State Model

Recommended states:

| state | meaning |
|---|---|
| created | task received by backend |
| queued | task pushed to queue |
| running | worker started execution |
| done | task successfully completed |
| failed | execution failed |

Optional future states:

| state | meaning |
|---|---|
| retrying | retry in progress |
| cancelled | manually cancelled |
| waiting_input | waiting for more user data |
| partial_done | partial result available |

This state model should be reflected consistently across:

- database
- worker logic
- backend responses
- Telegram user notifications

---

## 9. Reliability Design

To keep the platform stable as it grows, the following design principles should be preserved:

### Separation of concerns
Each component should do one primary job well:
- bot = user interaction
- backend = API/orchestration
- database = source of truth
- queue = transport
- worker = execution
- agents = intelligence

### Asynchronous processing
Long-running AI tasks should never block Telegram or HTTP request handling.

### Explicit task lifecycle
All task state transitions should be visible and persistent.

### Replaceable AI layer
The platform should allow switching or mixing AI providers without redesigning the whole system.

### Modular agent design
Specialized agent logic should be composable and independently improvable.

---

## 10. Recommended Repository Structure

```text
ai-assistant/
│
├── backend/
│   ├── app/
│   ├── Dockerfile
│   └── requirements.txt
│
├── bot/
│   ├── app/
│   ├── Dockerfile
│   └── requirements.txt
│
├── worker/
│   ├── app/
│   ├── Dockerfile
│   └── requirements.txt
│
├── infra/
│   └── docker-compose.yml
│
├── storage/
│
├── docs/
│   ├── project_context_v0.5.md
│   ├── architecture.md
│   └── system_design.md
│
└── .env
```

This repository structure is consistent with the documented project direction and existing layout. fileciteturn1file1 fileciteturn1file2

---

## 11. Development Model

Current development workflow:

- VS Code
- Remote SSH
- Git
- Docker
- Codex

Planned enhancement:

- OpenClaw as a separate development-agent environment on the same VPS, but not inside the main project runtime

This keeps the product runtime isolated while improving development speed.

---

## 12. Summary

AI Assistant Platform should be understood as:

- **not just a Telegram bot**
- **not just an API**
- **not just a prompt wrapper**

It is being designed as a **task execution platform** with a future **multi-agent orchestration layer**.

The core design pattern is:

```text
User Interface
→ Task Intake
→ Task Persistence
→ Task Queue
→ Worker Execution
→ AI Orchestration
→ Result Delivery
```

That design is the correct bridge from the current MVP toward the long-term multi-agent platform described in the project documentation. fileciteturn1file0 fileciteturn1file1 fileciteturn1file2
