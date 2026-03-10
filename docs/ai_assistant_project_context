# AI Assistant --- Project Context for AI Agents

## Purpose

This project builds a **Telegram-based AI assistant** that can accept
text tasks and documents, analyze them using LLMs, and return results
back to the user in Telegram.

Primary MVP use case: \> Upload a client document → AI analyzes it →
returns a concise summary of problems.

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
             LLM (OpenAI)
                │
                ▼
         Telegram delivery

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
execution input 6. send request to LLM 7. deliver result to Telegram

------------------------------------------------------------------------

## Executor Layer

Interface:

    TaskExecutor.execute(task) → ExecutionResult

ExecutionResult:

    success: bool
    result_text: str | None
    error_text: str | None

Executors available:

    mock
    openai
    deepseek (stub)
    kimi (stub)

Selected via environment variable:

    TASK_EXECUTOR=openai

------------------------------------------------------------------------

## Attachment Processing

Worker pipeline:

1.  Receive `telegram_file_id`
2.  Call Telegram API `getFile`
3.  Download file
4.  Save locally:

```{=html}
<!-- -->
```
    storage/input/<task_id>/<attachment_id>_<filename>

5.  Extract text

Supported formats:

    txt
    pdf
    docx

Extraction libraries:

    txt   → UTF‑8 decode
    pdf   → pypdf
    docx  → python-docx

------------------------------------------------------------------------

## Input Size Protection

Limits applied before sending data to LLM:

    EXECUTION_INPUT_MAX_CHARS = 120000
    ATTACHMENT_TEXT_MAX_CHARS = 50000
    INSTRUCTION_TEXT_MAX_CHARS = 8000

Diagnostic fields:

    extracted_text_length
    sent_text_length
    was_truncated

------------------------------------------------------------------------

## Telegram Result Delivery

Worker sends final result via:

    Telegram Bot API → sendMessage

Delivery fields stored in tasks:

    delivery_status
    delivered_at
    delivery_error

Statuses:

    pending
    delivered
    failed

------------------------------------------------------------------------

## Smoke Tests

Available project checks:

    make smoke
    make smoke-worker
    make smoke-task-attachment
    make smoke-attachment-extract-local
    make smoke-telegram-delivery

------------------------------------------------------------------------

## Current Status

The **end‑to‑end pipeline works**:

    Telegram → Bot → Backend → Redis → Worker → OpenAI → Telegram reply

Working features: - text task processing - document upload - attachment
extraction pipeline - OpenAI integration - Telegram result delivery -
smoke tests

------------------------------------------------------------------------

## Current Known Issue

When processing documents the worker fails to download attachments.

Example error:

    attachment download is unavailable:
    TELEGRAM_BOT_TOKEN is missing

This occurs during:

    Worker → Telegram API getFile

------------------------------------------------------------------------

## Root Cause

Worker is currently started manually:

    docker exec python -m app.worker_runtime

Environment variable

    TELEGRAM_BOT_TOKEN

is not always passed into the worker process.

Therefore worker cannot download Telegram attachments.

------------------------------------------------------------------------

## Next Engineering Tasks

1.  Ensure worker receives required environment variables.
2.  Stabilize worker runtime.
3.  Move worker into `docker-compose` service.
4.  Maintain compatibility with current MVP flow.

------------------------------------------------------------------------

## MVP Completion Status

System readiness:

    ≈ 95% complete

Remaining work focuses on **worker runtime reliability** and
**environment configuration**.
