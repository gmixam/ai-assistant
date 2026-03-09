# Task Execution System - Step 1 (PostgreSQL Task Storage)

## What changed
- Backend task storage moved from in-memory dictionary to PostgreSQL table `tasks`.
- `POST /tasks` contract for bot integration is preserved.
- Added `GET /tasks/{task_id}` for minimal read-back verification.

## Data model
Table: `tasks`
- `id` (UUID string, primary key)
- `input_text` (task input)
- `status` (default: `created`)
- `created_at` (UTC timestamp)
- `updated_at` (UTC timestamp)

## API behavior
### POST `/tasks`
Request:
```json
{
  "input_text": "Analyze client materials"
}
```

Response (MVP-safe and bot-compatible):
```json
{
  "id": "<task_id>",
  "task_id": "<task_id>",
  "status": "created",
  "created_at": "...",
  "updated_at": "..."
}
```

### GET `/tasks/{task_id}`
Response:
```json
{
  "id": "<task_id>",
  "input_text": "...",
  "status": "created",
  "created_at": "...",
  "updated_at": "..."
}
```

## Schema initialization (MVP-safe)
- No destructive migrations were introduced.
- Schema is initialized on backend startup with SQLAlchemy `create_all`.
- This is reversible and suitable for current MVP stage.
