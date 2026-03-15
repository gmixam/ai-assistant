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
                    provider_payload TEXT,
                    local_path TEXT,
                    download_status VARCHAR(32),
                    download_error TEXT,
                    extracted_text_length INTEGER,
                    sent_text_length INTEGER,
                    was_truncated BOOLEAN,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS mailbox_sync_states (
                    id SERIAL PRIMARY KEY,
                    provider VARCHAR(32) NOT NULL,
                    mailbox VARCHAR(255) NOT NULL,
                    checkpoint_json TEXT NOT NULL DEFAULT '{}',
                    last_status VARCHAR(32),
                    last_error TEXT,
                    last_synced_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS mailbox_policies (
                    id SERIAL PRIMARY KEY,
                    provider VARCHAR(32) NOT NULL,
                    mailbox VARCHAR(255) NOT NULL,
                    scope_mode VARCHAR(32) NOT NULL DEFAULT 'all',
                    scope_values_json TEXT NOT NULL DEFAULT '[]',
                    trusted_senders_json TEXT NOT NULL DEFAULT '[]',
                    trusted_domains_json TEXT NOT NULL DEFAULT '[]',
                    blocked_senders_json TEXT NOT NULL DEFAULT '[]',
                    blocked_domains_json TEXT NOT NULL DEFAULT '[]',
                    watch_senders_json TEXT NOT NULL DEFAULT '[]',
                    watch_domains_json TEXT NOT NULL DEFAULT '[]',
                    priority_rules_json TEXT NOT NULL DEFAULT '[]',
                    triage_thresholds_json TEXT NOT NULL DEFAULT '{}',
                    attachment_policy_json TEXT NOT NULL DEFAULT '{}',
                    rollout_mode VARCHAR(32) NOT NULL DEFAULT 'approval_only_for_deep',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS mail_routing_overrides (
                    id SERIAL PRIMARY KEY,
                    email_source_id INTEGER NOT NULL REFERENCES email_sources(id),
                    from_decision VARCHAR(32) NOT NULL,
                    to_decision VARCHAR(32) NOT NULL,
                    decided_by VARCHAR(255),
                    comment TEXT,
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
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_mailbox_sync_states_provider ON mailbox_sync_states(provider)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_mailbox_sync_states_mailbox ON mailbox_sync_states(mailbox)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_mailbox_policies_provider ON mailbox_policies(provider)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_mailbox_policies_mailbox ON mailbox_policies(mailbox)"))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_mail_routing_overrides_email_source_id ON mail_routing_overrides(email_source_id)")
        )
        connection.execute(text("ALTER TABLE email_sources ADD COLUMN IF NOT EXISTS applied_policy_json TEXT"))
        connection.execute(text("ALTER TABLE email_sources ADD COLUMN IF NOT EXISTS rule_hits_json TEXT"))
        connection.execute(text("ALTER TABLE email_sources ADD COLUMN IF NOT EXISTS decision_source VARCHAR(64)"))
        connection.execute(text("ALTER TABLE email_sources ADD COLUMN IF NOT EXISTS uncertain_reason TEXT"))
        connection.execute(text("ALTER TABLE email_sources ADD COLUMN IF NOT EXISTS rollout_mode VARCHAR(32)"))
        connection.execute(text("ALTER TABLE email_attachments ADD COLUMN IF NOT EXISTS provider_payload TEXT"))
        connection.execute(text("ALTER TABLE email_attachments ADD COLUMN IF NOT EXISTS local_path TEXT"))
        connection.execute(text("ALTER TABLE email_attachments ADD COLUMN IF NOT EXISTS download_status VARCHAR(32)"))
        connection.execute(text("ALTER TABLE email_attachments ADD COLUMN IF NOT EXISTS download_error TEXT"))
        connection.execute(text("ALTER TABLE email_attachments ADD COLUMN IF NOT EXISTS extracted_text_length INTEGER"))
        connection.execute(text("ALTER TABLE email_attachments ADD COLUMN IF NOT EXISTS sent_text_length INTEGER"))
        connection.execute(text("ALTER TABLE email_attachments ADD COLUMN IF NOT EXISTS was_truncated BOOLEAN"))
        connection.execute(text("ALTER TABLE mailbox_sync_states ADD COLUMN IF NOT EXISTS checkpoint_json TEXT"))
        connection.execute(text("ALTER TABLE mailbox_sync_states ADD COLUMN IF NOT EXISTS last_status VARCHAR(32)"))
        connection.execute(text("ALTER TABLE mailbox_sync_states ADD COLUMN IF NOT EXISTS last_error TEXT"))
        connection.execute(text("ALTER TABLE mailbox_sync_states ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMPTZ"))
        connection.execute(text("ALTER TABLE mailbox_sync_states ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ"))
        connection.execute(text("ALTER TABLE mailbox_sync_states ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ"))
        connection.execute(text("ALTER TABLE mailbox_policies ADD COLUMN IF NOT EXISTS scope_mode VARCHAR(32)"))
        connection.execute(text("ALTER TABLE mailbox_policies ADD COLUMN IF NOT EXISTS scope_values_json TEXT"))
        connection.execute(text("ALTER TABLE mailbox_policies ADD COLUMN IF NOT EXISTS trusted_senders_json TEXT"))
        connection.execute(text("ALTER TABLE mailbox_policies ADD COLUMN IF NOT EXISTS trusted_domains_json TEXT"))
        connection.execute(text("ALTER TABLE mailbox_policies ADD COLUMN IF NOT EXISTS blocked_senders_json TEXT"))
        connection.execute(text("ALTER TABLE mailbox_policies ADD COLUMN IF NOT EXISTS blocked_domains_json TEXT"))
        connection.execute(text("ALTER TABLE mailbox_policies ADD COLUMN IF NOT EXISTS watch_senders_json TEXT"))
        connection.execute(text("ALTER TABLE mailbox_policies ADD COLUMN IF NOT EXISTS watch_domains_json TEXT"))
        connection.execute(text("ALTER TABLE mailbox_policies ADD COLUMN IF NOT EXISTS priority_rules_json TEXT"))
        connection.execute(text("ALTER TABLE mailbox_policies ADD COLUMN IF NOT EXISTS triage_thresholds_json TEXT"))
        connection.execute(text("ALTER TABLE mailbox_policies ADD COLUMN IF NOT EXISTS attachment_policy_json TEXT"))
        connection.execute(text("ALTER TABLE mailbox_policies ADD COLUMN IF NOT EXISTS rollout_mode VARCHAR(32)"))
        connection.execute(text("ALTER TABLE mailbox_policies ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ"))
        connection.execute(text("ALTER TABLE mailbox_policies ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ"))
        connection.execute(text("ALTER TABLE mail_routing_overrides ADD COLUMN IF NOT EXISTS decided_by VARCHAR(255)"))
        connection.execute(text("ALTER TABLE mail_routing_overrides ADD COLUMN IF NOT EXISTS comment TEXT"))
        connection.execute(text("ALTER TABLE mail_routing_overrides ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ"))
