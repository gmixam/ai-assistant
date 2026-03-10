.PHONY: up ps debug-worker smoke smoke-worker smoke-worker-openai smoke-worker-openai-no-key smoke-telegram-metadata smoke-task-attachment smoke-attachment-extract-local smoke-telegram-delivery

up:
	docker compose -f infra/docker-compose.yml up -d --build

ps:
	docker compose -f infra/docker-compose.yml ps

debug-worker:
	docker exec -it ai_backend python -m app.worker_runtime --max-tasks 1

smoke:
	./scripts/smoke_task_flow.sh

smoke-worker:
	./scripts/smoke_worker_flow.sh

smoke-worker-openai:
	WORKER_MODE=debug TASK_EXECUTOR=openai EXPECTED_FINAL_STATUS=done ./scripts/smoke_worker_flow.sh

smoke-worker-openai-no-key:
	WORKER_MODE=debug TASK_EXECUTOR=openai EXPECTED_FINAL_STATUS=failed ./scripts/smoke_worker_flow.sh

smoke-telegram-metadata:
	./scripts/smoke_telegram_metadata_flow.sh

smoke-task-attachment:
	./scripts/smoke_task_attachment_flow.sh

smoke-attachment-extract-local:
	./scripts/smoke_attachment_extract_local.sh

smoke-telegram-delivery:
	./scripts/smoke_telegram_delivery_flow.sh
