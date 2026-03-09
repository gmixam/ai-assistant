from sqlalchemy import text
from sqlalchemy.engine import Engine


def ensure_task_optional_columns(engine: Engine) -> None:
    # MVP-safe, non-destructive schema evolution for existing deployments.
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS result_text TEXT"))
        connection.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS error_text TEXT"))
        connection.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS telegram_chat_id BIGINT"))
        connection.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS telegram_user_id BIGINT"))
        connection.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS telegram_message_id BIGINT"))
        connection.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS reply_to_message_id BIGINT"))
        connection.execute(text("ALTER TABLE task_attachments ADD COLUMN IF NOT EXISTS local_path TEXT"))
        connection.execute(text("ALTER TABLE task_attachments ADD COLUMN IF NOT EXISTS download_status VARCHAR(32)"))
        connection.execute(text("ALTER TABLE task_attachments ADD COLUMN IF NOT EXISTS download_error TEXT"))
