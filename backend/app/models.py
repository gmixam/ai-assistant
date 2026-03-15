from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True)
    input_text: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    result_text: Mapped[str | None] = mapped_column(String, nullable=True)
    error_text: Mapped[str | None] = mapped_column(String, nullable=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reply_to_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class TaskAttachment(Base):
    __tablename__ = "task_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    telegram_file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    local_path: Mapped[str | None] = mapped_column(String, nullable=True)
    download_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    download_error: Mapped[str | None] = mapped_column(String, nullable=True)
    extracted_text_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sent_text_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    was_truncated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class ApprovalItem(Base):
    __tablename__ = "approval_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    summary: Mapped[str] = mapped_column(String, nullable=False)
    proposed_action: Mapped[str | None] = mapped_column(String, nullable=True)
    structured_result: Mapped[str | None] = mapped_column(String, nullable=True)
    handoff: Mapped[str | None] = mapped_column(String, nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(String, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class EmailSource(Base):
    __tablename__ = "email_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    mailbox: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider_message_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    internet_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    from_address: Mapped[str] = mapped_column(String(255), nullable=False)
    from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    snippet: Mapped[str | None] = mapped_column(String, nullable=True)
    labels_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    attachments_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    duplicate_of_email_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("email_sources.id"), nullable=True)
    prefilter_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    triage_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    routing_decision: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    reason_codes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    applied_policy_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_hits_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uncertain_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    rollout_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=True, index=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class EmailAttachment(Base):
    __tablename__ = "email_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("email_sources.id"), nullable=False, index=True
    )
    provider_attachment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_inline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_path: Mapped[str | None] = mapped_column(String, nullable=True)
    download_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    download_error: Mapped[str | None] = mapped_column(String, nullable=True)
    extracted_text_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sent_text_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    was_truncated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class MailboxSyncState(Base):
    __tablename__ = "mailbox_sync_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    mailbox: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    checkpoint_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class MailboxPolicy(Base):
    __tablename__ = "mailbox_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    mailbox: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    scope_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="all")
    scope_values_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    trusted_senders_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    trusted_domains_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    blocked_senders_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    blocked_domains_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    watch_senders_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    watch_domains_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    priority_rules_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    triage_thresholds_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    attachment_policy_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    rollout_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="approval_only_for_deep")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class MailRoutingOverride(Base):
    __tablename__ = "mail_routing_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_source_id: Mapped[int] = mapped_column(Integer, ForeignKey("email_sources.id"), nullable=False, index=True)
    from_decision: Mapped[str] = mapped_column(String(32), nullable=False)
    to_decision: Mapped[str] = mapped_column(String(32), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    comment: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
