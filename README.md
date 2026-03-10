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

Primary operational references:
- [docs/task_execution_step7_telegram_e2e.md](/root/ai-assistant/docs/task_execution_step7_telegram_e2e.md)
- [docs/task_execution_step8_file_reading_mvp.md](/root/ai-assistant/docs/task_execution_step8_file_reading_mvp.md)
- [docs/smoke_tests.md](/root/ai-assistant/docs/smoke_tests.md)
