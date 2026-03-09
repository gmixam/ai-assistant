.PHONY: smoke smoke-worker

smoke:
	./scripts/smoke_task_flow.sh

smoke-worker:
	./scripts/smoke_worker_flow.sh
