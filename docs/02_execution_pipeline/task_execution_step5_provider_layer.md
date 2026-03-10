# Task Execution System - Step 5 (Provider Integration Layer)

## Goal
Prepare a provider-aware integration layer for future OpenAI/DeepSeek/Kimi execution without changing worker control flow.

## Executors structure
- `executors/base.py` - `TaskExecutor` contract and `ExecutionResult`
- `executors/mock.py` - working default executor
- `executors/openai_executor.py` - stub
- `executors/deepseek_executor.py` - stub
- `executors/kimi_executor.py` - stub
- `executors/provider_config.py` - normalized provider env config
- `executors/factory.py` - provider selection via `TASK_EXECUTOR`

## Provider selection
`TASK_EXECUTOR` values:
- `mock` (default)
- `openai`
- `deepseek`
- `kimi`

Unknown value behavior:
- controlled startup error (`ValueError`) from factory.

Why:
- fail-fast is safer than silent fallback for production-like runs.
- prevents accidental execution with wrong provider configuration.

## Stub behavior (no external API calls)
`openai/deepseek/kimi` executors:
- implement `TaskExecutor`
- return controlled failure result:
  - `success=False`
  - clear explanatory `error_text`
- do not perform network calls
- do not require API keys for this stage

## Provider config layer
`provider_config.load_provider_config(provider)` normalizes env inputs:
- OpenAI: `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_TIMEOUT_SECONDS`
- DeepSeek: `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `DEEPSEEK_TIMEOUT_SECONDS`
- Kimi: `KIMI_API_KEY`, `KIMI_MODEL`, `KIMI_TIMEOUT_SECONDS`

Keys/models/timeouts are optional at this stage; used for future real integrations.

## Worker flow impact
Worker flow is unchanged:
- dequeue task id
- load task
- set `processing`
- call selected executor via contract
- persist `done`+`result_text` or `failed`+`error_text`

## Smoke behavior
Default mock:
```bash
make smoke-worker
```

Stub providers (controlled failed lifecycle):
```bash
TASK_EXECUTOR=openai EXPECTED_FINAL_STATUS=failed make smoke-worker
TASK_EXECUTOR=deepseek EXPECTED_FINAL_STATUS=failed make smoke-worker
TASK_EXECUTOR=kimi EXPECTED_FINAL_STATUS=failed make smoke-worker
```
