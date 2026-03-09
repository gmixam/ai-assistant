# Task Execution System - Step 8 (Telegram Attachment Download + Text Extraction)

## Goal
Add real file reading to worker pipeline for Telegram document attachments:

`Telegram file_id -> getFile -> download -> local save -> text extraction -> executor input`

## Supported attachment types (MVP)
- `text/plain`
- `application/pdf`
- `application/vnd.openxmlformats-officedocument.wordprocessingml.document` (`.docx`)

## Storage path
Downloaded files are stored under:

`storage/input/<task_id>/<attachment_id>_<sanitized_filename>`

Path is configurable via `STORAGE_INPUT_DIR` (default: `storage/input`).

## Attachment diagnostic fields
`task_attachments` now stores:
- `local_path`
- `download_status` (`pending`, `downloading`, `downloaded`, `failed`)
- `download_error`
- `extracted_text_length`
- `sent_text_length`
- `was_truncated`

## Input size control layer (MVP)
Execution input is now size-guarded before executor call:
- `EXECUTION_INPUT_MAX_CHARS` (default: `120000`) - total budget for composed execution input.
- `ATTACHMENT_TEXT_MAX_CHARS` (default: `50000`) - per-attachment cap before global budget.
- `INSTRUCTION_TEXT_MAX_CHARS` (default: `8000`) - cap for task instruction text.

When extracted text exceeds limits:
- worker sends only a controlled truncated subset to executor
- task does not fail only because of large size
- diagnostics are stored in attachment rows (`extracted_text_length`, `sent_text_length`, `was_truncated`)
- worker logs total extracted/sent lengths and truncation flag.

## Worker behavior
1. Worker loads task attachments.
2. For each attachment:
   - Calls Telegram Bot API `getFile` using `telegram_file_id`
   - Downloads binary content from Telegram file endpoint
   - Saves file locally
   - Extracts text by MIME type
3. Builds execution input:
   - `Instruction: <task.input_text>`
   - plus extracted content blocks per attachment
4. Passes merged input to executor.

If any attachment fails download or extraction:
- task moves to `failed`
- `error_text` contains readable reason
- worker loop continues processing next tasks

## Smoke/manual checks
Base checks:
```bash
make smoke
make smoke-worker
```

Attachment metadata API smoke:
```bash
make smoke-task-attachment
```

Local extraction smoke (`txt` + `docx`, optional `pdf`):
```bash
make smoke-attachment-extract-local
# optional pdf check:
PDF_SAMPLE_PATH=/absolute/path/to/sample.pdf make smoke-attachment-extract-local
```

## Manual Telegram test
1. Send `document + caption` (`txt`, `pdf`, or `docx`).
2. Wait for bot ack with task id.
3. Wait for worker result message.
4. Check `GET /tasks/{task_id}`:
   - attachment `download_status` should be `downloaded`
   - attachment `local_path` should be filled
5. For unsupported MIME or broken file:
   - task should become `failed`
   - `error_text` should explain the failure.
