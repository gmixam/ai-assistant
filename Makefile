.PHONY: smoke smoke-worker smoke-worker-openai smoke-worker-openai-no-key smoke-telegram-metadata

smoke:
	./scripts/smoke_task_flow.sh

smoke-worker:
	./scripts/smoke_worker_flow.sh

smoke-worker-openai:
	TASK_EXECUTOR=openai EXPECTED_FINAL_STATUS=done ./scripts/smoke_worker_flow.sh

smoke-worker-openai-no-key:
	TASK_EXECUTOR=openai EXPECTED_FINAL_STATUS=failed ./scripts/smoke_worker_flow.sh

smoke-telegram-metadata:
	./scripts/smoke_telegram_metadata_flow.sh
