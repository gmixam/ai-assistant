from sqlalchemy import text
from sqlalchemy.engine import Engine


def ensure_task_optional_columns(engine: Engine) -> None:
    # MVP-safe, non-destructive schema evolution for existing deployments.
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS result_text TEXT"))
        connection.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS error_text TEXT"))
