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
        connection.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(32)"))
        connection.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ"))
        connection.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS delivery_error TEXT"))
        connection.execute(text("ALTER TABLE task_attachments ADD COLUMN IF NOT EXISTS local_path TEXT"))
        connection.execute(text("ALTER TABLE task_attachments ADD COLUMN IF NOT EXISTS download_status VARCHAR(32)"))
        connection.execute(text("ALTER TABLE task_attachments ADD COLUMN IF NOT EXISTS download_error TEXT"))
        connection.execute(text("ALTER TABLE task_attachments ADD COLUMN IF NOT EXISTS extracted_text_length INTEGER"))
        connection.execute(text("ALTER TABLE task_attachments ADD COLUMN IF NOT EXISTS sent_text_length INTEGER"))
        connection.execute(text("ALTER TABLE task_attachments ADD COLUMN IF NOT EXISTS was_truncated BOOLEAN"))
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS approval_items (
                    id SERIAL PRIMARY KEY,
                    task_id VARCHAR(36) NOT NULL REFERENCES tasks(id),
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    summary TEXT NOT NULL,
                    proposed_action TEXT,
                    structured_result TEXT,
                    handoff TEXT,
                    decision_comment TEXT,
                    decided_by VARCHAR(255),
                    decided_at TIMESTAMPTZ,
                    expires_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_approval_items_task_id ON approval_items(task_id)"))
        connection.execute(text("ALTER TABLE approval_items ADD COLUMN IF NOT EXISTS proposed_action TEXT"))
        connection.execute(text("ALTER TABLE approval_items ADD COLUMN IF NOT EXISTS structured_result TEXT"))
        connection.execute(text("ALTER TABLE approval_items ADD COLUMN IF NOT EXISTS handoff TEXT"))
        connection.execute(text("ALTER TABLE approval_items ADD COLUMN IF NOT EXISTS decision_comment TEXT"))
        connection.execute(text("ALTER TABLE approval_items ADD COLUMN IF NOT EXISTS decided_by VARCHAR(255)"))
        connection.execute(text("ALTER TABLE approval_items ADD COLUMN IF NOT EXISTS decided_at TIMESTAMPTZ"))
        connection.execute(text("ALTER TABLE approval_items ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ"))
        connection.execute(text("ALTER TABLE approval_items ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ"))
        connection.execute(text("ALTER TABLE approval_items ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ"))
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS email_sources (
                    id SERIAL PRIMARY KEY,
                    provider VARCHAR(32) NOT NULL,
                    mailbox VARCHAR(255) NOT NULL,
                    provider_message_id VARCHAR(255) NOT NULL,
                    thread_id VARCHAR(255),
                    internet_message_id VARCHAR(255),
                    from_address VARCHAR(255) NOT NULL,
                    from_name VARCHAR(255),
                    subject TEXT,
                    snippet TEXT,
                    labels_json TEXT NOT NULL DEFAULT '[]',
                    attachments_count INTEGER NOT NULL DEFAULT 0,
                    source_payload TEXT,
                    dedupe_key VARCHAR(255) NOT NULL,
                    duplicate_of_email_id INTEGER REFERENCES email_sources(id),
                    prefilter_status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    triage_score INTEGER NOT NULL DEFAULT 0,
                    routing_decision VARCHAR(32) NOT NULL DEFAULT 'pending',
                    reason_codes_json TEXT NOT NULL DEFAULT '[]',
                    task_id VARCHAR(36) REFERENCES tasks(id),
                    received_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS email_attachments (
                    id SERIAL PRIMARY KEY,
                    email_source_id INTEGER NOT NULL REFERENCES email_sources(id),
                    provider_attachment_id VARCHAR(255),
                    filename VARCHAR(255),
                    mime_type VARCHAR(255),
                    file_size INTEGER,
                    is_inline BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_email_sources_provider ON email_sources(provider)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_email_sources_mailbox ON email_sources(mailbox)"))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_email_sources_provider_message_id ON email_sources(provider_message_id)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_email_sources_internet_message_id ON email_sources(internet_message_id)")
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_email_sources_dedupe_key ON email_sources(dedupe_key)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_email_sources_task_id ON email_sources(task_id)"))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_email_attachments_email_source_id ON email_attachments(email_source_id)")
        )
