.PHONY: up ps worker-up worker-stop debug-worker smoke smoke-normal smoke-worker smoke-worker-debug smoke-worker-openai smoke-worker-openai-no-key smoke-telegram-metadata smoke-task-attachment smoke-attachment-extract-local smoke-telegram-delivery smoke-contract smoke-approval smoke-email-intake smoke-email-team smoke-mail-provider smoke-mail-policy

up:
	docker compose -f infra/docker-compose.yml up -d --build

ps:
	docker compose -f infra/docker-compose.yml ps

worker-up:
	docker compose -f infra/docker-compose.yml up -d worker

worker-stop:
	docker compose -f infra/docker-compose.yml stop worker || true

debug-worker:
	docker exec -it ai_backend python -m app.worker_runtime --max-tasks 1

smoke:
	docker compose -f infra/docker-compose.yml stop worker || true
	./scripts/smoke_task_flow.sh

smoke-normal:
	docker compose -f infra/docker-compose.yml up -d worker
	./scripts/smoke_worker_flow.sh

smoke-worker:
	./scripts/smoke_worker_flow.sh

smoke-worker-debug:
	docker compose -f infra/docker-compose.yml stop worker || true
	WORKER_MODE=debug ./scripts/smoke_worker_flow.sh

smoke-worker-openai:
	docker compose -f infra/docker-compose.yml stop worker || true
	WORKER_MODE=debug TASK_EXECUTOR=openai EXPECTED_FINAL_STATUS=done ./scripts/smoke_worker_flow.sh

smoke-worker-openai-no-key:
	docker compose -f infra/docker-compose.yml stop worker || true
	WORKER_MODE=debug TASK_EXECUTOR=openai EXPECTED_FINAL_STATUS=failed ./scripts/smoke_worker_flow.sh

smoke-telegram-metadata:
	./scripts/smoke_telegram_metadata_flow.sh

smoke-task-attachment:
	./scripts/smoke_task_attachment_flow.sh

smoke-attachment-extract-local:
	./scripts/smoke_attachment_extract_local.sh

smoke-telegram-delivery:
	docker compose -f infra/docker-compose.yml stop worker || true
	./scripts/smoke_telegram_delivery_flow.sh

smoke-contract:
	docker compose -f infra/docker-compose.yml up -d --build backend worker
	./scripts/smoke_contract_execution.sh

smoke-approval:
	docker compose -f infra/docker-compose.yml up -d --build backend bot
	./scripts/smoke_approval_flow.sh

smoke-email-intake:
	docker compose -f infra/docker-compose.yml stop worker || true
	./scripts/smoke_email_intake_flow.sh

smoke-email-team:
	docker compose -f infra/docker-compose.yml stop worker || true
	./scripts/smoke_email_team_flow.sh

smoke-mail-provider:
	docker compose -f infra/docker-compose.yml stop worker || true
	./scripts/smoke_mail_provider_flow.sh

smoke-mail-policy:
	docker compose -f infra/docker-compose.yml stop worker || true
	./scripts/smoke_mail_policy_flow.sh
