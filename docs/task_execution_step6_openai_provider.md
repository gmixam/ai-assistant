# Task Execution System - Step 6 (OpenAI Real Provider)

## Goal
Enable first real AI provider integration through the existing provider-aware executor layer: OpenAI.

## What changed
- `openai_executor.py` now performs a real HTTP call to OpenAI Chat Completions API.
- Worker flow remains unchanged and still uses `TaskExecutor.execute(task) -> ExecutionResult`.
- Missing key and runtime errors are handled as controlled failed results (`success=False`, `error_text=...`).

## OpenAI env configuration
Used by provider config:
- `OPENAI_API_KEY` (required for successful real call)
- `OPENAI_MODEL` (default: `gpt-4o-mini`)
- `OPENAI_TIMEOUT_SECONDS` (default: `30`)
- `OPENAI_BASE_URL` (default: `https://api.openai.com`)

## Controlled fail-path behavior
If `OPENAI_API_KEY` is missing:
- executor returns `ExecutionResult(success=False, error_text="OpenAI API key is missing ...")`
- worker marks task as `failed`
- worker loop keeps running (no crash)

If HTTP/network/parse errors happen:
- executor returns normalized `error_text`
- no unhandled traceback escapes to worker loop

## Smoke and verification
Default (mock):
```bash
make smoke
make smoke-worker
```

OpenAI without key (controlled fail):
```bash
make smoke-worker-openai-no-key
```

OpenAI with key (expected success):
```bash
export OPENAI_API_KEY=...
make smoke-worker-openai
```

Expected with key:
- worker lifecycle reaches `done`
- `result_text` contains model output
