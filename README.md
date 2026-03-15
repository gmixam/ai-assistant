# ai-assistant

## Current MVP status
The current normal operation mode is Docker Compose with dedicated long-running services:
- `ai_bot`
- `ai_backend`
- `ai_worker`
- `ai_postgres`
- `ai_redis`

`ai_worker` is the standard runtime for queue consumption, attachment processing, AI execution, and Telegram delivery.

Manual worker start inside `ai_backend` is diagnostic/fallback only:
```bash
docker exec -it ai_backend python -m app.worker_runtime --max-tasks 1
```

## Normal startup
```bash
make up
make ps
```

## MVP document analysis goal
Target user flow:

`Telegram document -> attachment download -> text extraction -> AI analysis -> Telegram reply`

## Email intake foundation
The current mailbox intake foundation is provider-agnostic in core logic and adds a first live adapter for `mailru_imap` plus deterministic `fake` provider for smoke:

`mailbox intake -> deterministic pre-filter -> cheap triage -> routing decision (ignore/light/deep)`

Only `deep` emails create execution tasks. `ignore` and `light` emails stay persisted as `email_sources` plus `email_attachments` metadata for later review and future workflow expansion.

Provider-specific responsibilities now sit behind a common contract:
- fetch new messages
- fetch one message
- download attachment
- checkpoint / sync state
- normalize provider payload

Current first live provider path:
- `mailru_imap` for Mail.ru / VK-hosted corporate mailbox access
- `fake` for deterministic provider smoke

Deep email tasks now route into `email_triage_team`:

`email source -> deep task -> email_triage_agent -> action_extraction_agent -> attachment_analysis_agent (optional) -> approval_prep_agent -> approval item`

If the deep email task carries Telegram metadata, approval delivery is sent to Telegram from the worker flow.

Primary operational references:
- [task_execution_step7_telegram_e2e.md](/root/ai-assistant/docs/02_execution_pipeline/task_execution_step7_telegram_e2e.md)
- [task_execution_step8_file_reading_mvp.md](/root/ai-assistant/docs/02_execution_pipeline/task_execution_step8_file_reading_mvp.md)
- [smoke_tests.md](/root/ai-assistant/docs/03_operations/smoke_tests.md)
