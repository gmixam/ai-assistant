import json
from dataclasses import dataclass
from hashlib import sha256
from uuid import uuid4

from sqlalchemy.orm import Session

from .models import EmailAttachment, EmailSource, Task
from .queue import enqueue_task
from .tasks import GmailIntakeRequest

PROVIDER_GMAIL = "gmail"

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


@dataclass
class IntakeDecision:
    prefilter_status: str
    triage_score: int
    routing_decision: str
    reason_codes: list[str]


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def _normalize_text(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def build_dedupe_key(payload: GmailIntakeRequest) -> str:
    if payload.internet_message_id:
        return f"internet:{_normalize_text(payload.internet_message_id)}"
    if payload.provider_message_id:
        return f"provider:{_normalize_text(payload.provider_message_id)}"
    base = "|".join(
        [
            payload.mailbox.strip().lower(),
            _normalize_email(payload.from_address),
            _normalize_text(payload.subject),
            _normalize_text(payload.snippet),
        ]
    )
    return "content:" + sha256(base.encode("utf-8")).hexdigest()


def _is_auto_sender(from_address: str) -> bool:
    sender = _normalize_email(from_address)
    return "no-reply@" in sender or "noreply@" in sender or "mailer-daemon@" in sender


def evaluate_intake(payload: GmailIntakeRequest) -> IntakeDecision:
    subject = _normalize_text(payload.subject)
    snippet = _normalize_text(payload.snippet)
    labels = {_normalize_text(label) for label in payload.labels}
    reason_codes: list[str] = []

    if labels & IGNORED_LABELS:
        reason_codes.append("prefilter_label_ignored")
        return IntakeDecision("ignored", 0, "ignore", reason_codes)
    if _is_auto_sender(payload.from_address):
        reason_codes.append("prefilter_auto_sender")
        return IntakeDecision("ignored", 0, "ignore", reason_codes)
    if "out of office" in subject or "automatic reply" in subject or "autoreply" in subject:
        reason_codes.append("prefilter_autoreply")
        return IntakeDecision("ignored", 0, "ignore", reason_codes)

    score = 0
    if payload.attachments:
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
    if score >= 60 or (payload.attachments and score >= 40):
        routing_decision = "deep"
        reason_codes.append("route_deep_threshold")
    elif score >= 25:
        routing_decision = "light"
        reason_codes.append("route_light_threshold")
    else:
        routing_decision = "ignore"
        reason_codes.append("route_ignore_threshold")

    return IntakeDecision("passed", score, routing_decision, reason_codes)


def create_deep_task(email_source: EmailSource, payload: GmailIntakeRequest, db: Session) -> Task:
    subject = (payload.subject or "").strip() or "(no subject)"
    snippet = (payload.snippet or "").strip()
    attachment_summary = ", ".join(
        filter(None, [attachment.filename or attachment.mime_type for attachment in payload.attachments])
    )
    task_input = (
        f"Email deep triage\n"
        f"provider={email_source.provider}\n"
        f"mailbox={email_source.mailbox}\n"
        f"email_source_id={email_source.id}\n"
        f"from={payload.from_address}\n"
        f"subject={subject}\n"
        f"snippet={snippet}\n"
        f"attachments={attachment_summary or 'none'}"
    )
    task = Task(id=str(uuid4()), input_text=task_input, status="created")
    db.add(task)
    db.flush()
    enqueue_task(task.id)
    task.status = "queued"
    email_source.task_id = task.id
    return task


def persist_gmail_intake(payload: GmailIntakeRequest, db: Session) -> EmailSource:
    dedupe_key = build_dedupe_key(payload)
    existing = (
        db.query(EmailSource)
        .filter(EmailSource.provider == PROVIDER_GMAIL, EmailSource.mailbox == payload.mailbox, EmailSource.dedupe_key == dedupe_key)
        .order_by(EmailSource.id.asc())
        .first()
    )

    labels = [label.strip() for label in payload.labels if label.strip()]
    decision = evaluate_intake(payload)
    email_source = EmailSource(
        provider=PROVIDER_GMAIL,
        mailbox=payload.mailbox,
        provider_message_id=payload.provider_message_id,
        thread_id=payload.thread_id,
        internet_message_id=payload.internet_message_id,
        from_address=payload.from_address.strip(),
        from_name=(payload.from_name or "").strip() or None,
        subject=(payload.subject or "").strip() or None,
        snippet=(payload.snippet or "").strip() or None,
        labels_json=json.dumps(labels),
        attachments_count=len(payload.attachments),
        source_payload=payload.json(),
        dedupe_key=dedupe_key,
        duplicate_of_email_id=existing.id if existing is not None else None,
        prefilter_status="duplicate" if existing is not None else decision.prefilter_status,
        triage_score=0 if existing is not None else decision.triage_score,
        routing_decision="ignore" if existing is not None else decision.routing_decision,
        reason_codes_json=json.dumps(
            ["dedupe_duplicate_message"] if existing is not None else decision.reason_codes
        ),
        received_at=payload.received_at,
    )
    db.add(email_source)
    db.flush()

    for attachment in payload.attachments:
        db.add(
            EmailAttachment(
                email_source_id=email_source.id,
                provider_attachment_id=attachment.provider_attachment_id,
                filename=attachment.filename,
                mime_type=attachment.mime_type,
                file_size=attachment.file_size,
                is_inline=attachment.is_inline,
            )
        )

    if existing is None and decision.routing_decision == "deep":
        create_deep_task(email_source, payload, db)

    db.commit()
    db.refresh(email_source)
    return email_source
