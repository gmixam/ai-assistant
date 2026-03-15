import json
import logging
from dataclasses import dataclass
from hashlib import sha256
from uuid import uuid4

from sqlalchemy.orm import Session

from .mail_models import NormalizedMailAttachment, NormalizedMailMessage, attachment_to_json, message_to_json
from .mail_policy import apply_policy, load_mailbox_policy
from .models import EmailAttachment, EmailSource, Task
from .queue import enqueue_task
from .tasks import GmailIntakeRequest

ACTION_TERMS = (
    "action required",
    "approve",
    "approval",
    "asap",
    "contract",
    "deadline",
    "invoice",
    "payment",
    "proposal",
    "quote",
    "request",
    "review",
    "urgent",
)
HIGH_PRIORITY_TERMS = (
    "approve",
    "contract",
    "deadline",
    "invoice",
    "payment",
    "urgent",
)
MARKETING_TERMS = (
    "discount",
    "newsletter",
    "sale",
    "unsubscribe",
    "webinar",
)
IGNORED_LABELS = {"spam", "trash"}
LOW_SIGNAL_LABELS = {"promotions", "social", "forums", "updates"}
logger = logging.getLogger("email_intake")


@dataclass
class IntakeDecision:
    prefilter_status: str
    triage_score: int
    routing_decision: str
    reason_codes: list[str]


def gmail_request_to_normalized(payload: GmailIntakeRequest) -> NormalizedMailMessage:
    attachments = [
        NormalizedMailAttachment(
            attachment_id=str(item.provider_attachment_id or index),
            filename=item.filename,
            mime_type=item.mime_type,
            file_size=item.file_size,
            is_inline=item.is_inline,
            provider_payload=dict(item.provider_payload or {}),
        )
        for index, item in enumerate(payload.attachments, start=1)
    ]
    return NormalizedMailMessage(
        provider="gmail",
        mailbox=payload.mailbox,
        provider_message_id=payload.provider_message_id,
        thread_id=payload.thread_id,
        internet_message_id=payload.internet_message_id,
        from_address=payload.from_address,
        from_name=payload.from_name,
        subject=payload.subject,
        snippet=payload.snippet,
        labels=list(payload.labels),
        attachments=attachments,
        telegram_chat_id=payload.telegram_chat_id,
        telegram_user_id=payload.telegram_user_id,
        telegram_message_id=payload.telegram_message_id,
        reply_to_message_id=payload.reply_to_message_id,
        received_at=payload.received_at,
    )


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def _normalize_text(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def build_dedupe_key(message: NormalizedMailMessage) -> str:
    if message.internet_message_id:
        return f"internet:{_normalize_text(message.internet_message_id)}"
    if message.provider_message_id:
        return f"provider:{_normalize_text(message.provider_message_id)}"
    base = "|".join(
        [
            message.mailbox.strip().lower(),
            _normalize_email(message.from_address),
            _normalize_text(message.subject),
            _normalize_text(message.snippet),
        ]
    )
    return "content:" + sha256(base.encode("utf-8")).hexdigest()


def _is_auto_sender(from_address: str) -> bool:
    sender = _normalize_email(from_address)
    return "no-reply@" in sender or "noreply@" in sender or "mailer-daemon@" in sender


def evaluate_intake(message: NormalizedMailMessage) -> IntakeDecision:
    subject = _normalize_text(message.subject)
    snippet = _normalize_text(message.snippet)
    labels = {_normalize_text(label) for label in message.labels}
    reason_codes: list[str] = []

    if labels & IGNORED_LABELS:
        reason_codes.append("prefilter_label_ignored")
        return IntakeDecision("ignored", 0, "ignore", reason_codes)
    if _is_auto_sender(message.from_address):
        reason_codes.append("prefilter_auto_sender")
        return IntakeDecision("ignored", 0, "ignore", reason_codes)
    if "out of office" in subject or "automatic reply" in subject or "autoreply" in subject:
        reason_codes.append("prefilter_autoreply")
        return IntakeDecision("ignored", 0, "ignore", reason_codes)

    score = 0
    if message.attachments:
        score += 35
        reason_codes.append("triage_has_attachment")
    if any(term in subject or term in snippet for term in ACTION_TERMS):
        score += 35
        reason_codes.append("triage_action_language")
    if any(term in subject or term in snippet for term in HIGH_PRIORITY_TERMS):
        score += 20
        reason_codes.append("triage_high_priority_language")
    if labels & LOW_SIGNAL_LABELS:
        score -= 20
        reason_codes.append("triage_low_signal_label")
    if any(term in subject or term in snippet for term in MARKETING_TERMS):
        score -= 20
        reason_codes.append("triage_marketing_language")
    if len(snippet) >= 40:
        score += 10
        reason_codes.append("triage_rich_snippet")
    if "fw:" in subject or "fwd:" in subject or "re:" in subject:
        score += 5
        reason_codes.append("triage_thread_continuation")

    score = max(0, min(score, 100))
    if score >= 60 or (message.attachments and score >= 40):
        routing_decision = "deep"
        reason_codes.append("route_deep_threshold")
    elif score >= 25:
        routing_decision = "light"
        reason_codes.append("route_light_threshold")
    else:
        routing_decision = "ignore"
        reason_codes.append("route_ignore_threshold")

    return IntakeDecision("passed", score, routing_decision, reason_codes)


def create_deep_task(email_source: EmailSource, message: NormalizedMailMessage, db: Session) -> Task:
    subject = (message.subject or "").strip() or "(no subject)"
    snippet = (message.snippet or "").strip()
    attachment_summary = ", ".join(
        filter(None, [attachment.filename or attachment.mime_type for attachment in message.attachments])
    )
    task_input = (
        f"Email deep triage\n"
        f"provider={email_source.provider}\n"
        f"mailbox={email_source.mailbox}\n"
        f"email_source_id={email_source.id}\n"
        f"from={message.from_address}\n"
        f"subject={subject}\n"
        f"snippet={snippet}\n"
        f"attachments={attachment_summary or 'none'}"
    )
    task = Task(
        id=str(uuid4()),
        input_text=task_input,
        status="created",
        telegram_chat_id=message.telegram_chat_id,
        telegram_user_id=message.telegram_user_id,
        telegram_message_id=message.telegram_message_id,
        reply_to_message_id=message.reply_to_message_id,
        delivery_status="pending" if message.telegram_chat_id is not None else None,
    )
    db.add(task)
    db.flush()
    enqueue_task(task.id)
    task.status = "queued"
    email_source.task_id = task.id
    return task


def persist_normalized_mail_message(message: NormalizedMailMessage, db: Session) -> EmailSource:
    dedupe_key = build_dedupe_key(message)
    existing = (
        db.query(EmailSource)
        .filter(
            EmailSource.provider == message.provider,
            EmailSource.mailbox == message.mailbox,
            EmailSource.dedupe_key == dedupe_key,
        )
        .order_by(EmailSource.id.asc())
        .first()
    )

    labels = [label.strip() for label in message.labels if label.strip()]
    base_decision = evaluate_intake(message)
    policy = load_mailbox_policy(message.provider, message.mailbox, db)
    decision = apply_policy(
        message,
        base_decision.prefilter_status,
        base_decision.triage_score,
        base_decision.routing_decision,
        base_decision.reason_codes,
        policy,
    )
    email_source = EmailSource(
        provider=message.provider,
        mailbox=message.mailbox,
        provider_message_id=message.provider_message_id,
        thread_id=message.thread_id,
        internet_message_id=message.internet_message_id,
        from_address=message.from_address.strip(),
        from_name=(message.from_name or "").strip() or None,
        subject=(message.subject or "").strip() or None,
        snippet=(message.snippet or "").strip() or None,
        labels_json=json.dumps(labels),
        attachments_count=len(message.attachments),
        source_payload=message_to_json(message),
        dedupe_key=dedupe_key,
        duplicate_of_email_id=existing.id if existing is not None else None,
        prefilter_status="duplicate" if existing is not None else base_decision.prefilter_status,
        triage_score=0 if existing is not None else decision.triage_score,
        routing_decision="ignore" if existing is not None else decision.routing_decision,
        reason_codes_json=json.dumps(["dedupe_duplicate_message"] if existing is not None else decision.reason_codes),
        applied_policy_json=json.dumps({} if existing is not None else decision.applied_policy),
        rule_hits_json=json.dumps(["dedupe_duplicate_message"] if existing is not None else decision.rule_hits),
        decision_source="dedupe" if existing is not None else decision.decision_source,
        uncertain_reason=None if existing is not None else decision.uncertain_reason,
        rollout_mode=None if existing is not None else decision.rollout_mode,
        received_at=message.received_at,
    )
    db.add(email_source)
    db.flush()

    for attachment in message.attachments:
        db.add(
            EmailAttachment(
                email_source_id=email_source.id,
                provider_attachment_id=attachment.attachment_id,
                filename=attachment.filename,
                mime_type=attachment.mime_type,
                file_size=attachment.file_size,
                is_inline=attachment.is_inline,
                provider_payload=attachment_to_json(attachment),
                download_status="pending"
                if existing is None and decision.routing_decision == "deep" and decision.attachment_download_allowed
                else None,
            )
        )

    if existing is None and decision.create_deep_task:
        create_deep_task(email_source, message, db)

    db.commit()
    db.refresh(email_source)
    logger.info(
        "event=mail_routing_finalized provider=%s mailbox=%s provider_message_id=%s routing_decision=%s decision_source=%s rollout_mode=%s",
        message.provider,
        message.mailbox,
        message.provider_message_id,
        email_source.routing_decision,
        email_source.decision_source or "unknown",
        email_source.rollout_mode or "none",
    )
    return email_source


def persist_gmail_intake(payload: GmailIntakeRequest, db: Session) -> EmailSource:
    return persist_normalized_mail_message(gmail_request_to_normalized(payload), db)
