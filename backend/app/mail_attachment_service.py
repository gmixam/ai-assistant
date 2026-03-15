import json
import logging
import os
from pathlib import Path

from sqlalchemy.orm import Session

from .attachment_pipeline import (
    ATTACHMENT_TEXT_MAX_CHARS,
    EXECUTION_INPUT_MAX_CHARS,
    ExtractedAttachment,
    compose_controlled_execution_input,
    extract_text_from_attachment_bytes,
)
from .mail_models import DownloadedMailAttachment, NormalizedMailAttachment
from .mail_providers.registry import MailProviderRegistry
from .models import EmailAttachment, EmailSource

logger = logging.getLogger("mail_attachment_service")

STORAGE_INPUT_DIR = os.getenv("STORAGE_INPUT_DIR", "storage/input")


def build_email_attachment_analysis_text(
    email_source: EmailSource,
    attachments: list[EmailAttachment],
    registry: MailProviderRegistry,
    db: Session,
) -> str:
    extracted_attachments: list[ExtractedAttachment] = []
    for attachment in attachments:
        downloaded = _download_attachment(email_source, attachment, registry, db)
        extracted_text = extract_text_from_attachment_bytes(downloaded.payload, downloaded.mime_type)
        extracted_attachments.append(
            ExtractedAttachment(
                attachment_id=attachment.id,
                filename=downloaded.filename,
                mime_type=downloaded.mime_type,
                local_path=attachment.local_path or "",
                extracted_text=extracted_text,
            )
        )

    prepared = compose_controlled_execution_input(
        f"Analyze email attachments for email_source_id={email_source.id}",
        extracted_attachments,
        max_input_chars=EXECUTION_INPUT_MAX_CHARS,
        per_attachment_max_chars=ATTACHMENT_TEXT_MAX_CHARS,
    )
    attachment_by_id = {attachment.id: attachment for attachment in attachments}
    for item in extracted_attachments:
        target = attachment_by_id[item.attachment_id]
        sent_len = prepared.sent_text_length_by_attachment_id.get(item.attachment_id, 0)
        target.extracted_text_length = len(item.extracted_text)
        target.sent_text_length = sent_len
        target.was_truncated = sent_len < len(item.extracted_text)
    db.commit()
    return prepared.text


def _download_attachment(
    email_source: EmailSource,
    attachment: EmailAttachment,
    registry: MailProviderRegistry,
    db: Session,
) -> DownloadedMailAttachment:
    applied_policy = _load_applied_policy(email_source)
    attachment_policy = applied_policy.get("attachment_policy") if isinstance(applied_policy.get("attachment_policy"), dict) else {}
    if "deep" not in set(attachment_policy.get("download_for") or ["deep"]):
        raise RuntimeError("attachment download is disabled by mailbox policy")
    attachment.download_status = "downloading"
    attachment.download_error = None
    db.commit()
    db.refresh(attachment)

    logger.info(
        "event=mail_attachment_download_started provider=%s mailbox=%s email_source_id=%s attachment_id=%s",
        email_source.provider,
        email_source.mailbox,
        email_source.id,
        attachment.id,
    )
    adapter = registry.resolve(email_source.provider)
    normalized_attachment = _build_normalized_attachment(attachment)
    try:
        downloaded = adapter.download_attachment(
            email_source.mailbox,
            email_source.provider_message_id,
            normalized_attachment,
            options=_provider_options(email_source),
        )
        local_path = _store_payload(email_source.id, attachment.id, downloaded.filename, downloaded.payload)
        attachment.local_path = local_path
        attachment.download_status = "downloaded"
        attachment.download_error = None
        db.commit()
        db.refresh(attachment)
        logger.info(
            "event=mail_attachment_download_completed provider=%s mailbox=%s email_source_id=%s attachment_id=%s bytes=%s",
            email_source.provider,
            email_source.mailbox,
            email_source.id,
            attachment.id,
            len(downloaded.payload),
        )
        return downloaded
    except Exception as exc:
        attachment.download_status = "failed"
        attachment.download_error = str(exc)[:1000]
        db.commit()
        db.refresh(attachment)
        logger.error(
            "event=mail_attachment_download_failed provider=%s mailbox=%s email_source_id=%s attachment_id=%s error=%s",
            email_source.provider,
            email_source.mailbox,
            email_source.id,
            attachment.id,
            exc,
        )
        raise


def _build_normalized_attachment(attachment: EmailAttachment) -> NormalizedMailAttachment:
    try:
        provider_payload = json.loads(attachment.provider_payload or "{}")
    except (TypeError, ValueError):
        provider_payload = {}
    return NormalizedMailAttachment(
        attachment_id=attachment.provider_attachment_id or str(attachment.id),
        filename=attachment.filename,
        mime_type=attachment.mime_type,
        file_size=attachment.file_size,
        is_inline=bool(attachment.is_inline),
        provider_payload=provider_payload if isinstance(provider_payload, dict) else {},
    )


def _provider_options(email_source: EmailSource) -> dict | None:
    try:
        source_payload = json.loads(email_source.source_payload or "{}")
    except (TypeError, ValueError):
        return None
    if not isinstance(source_payload, dict):
        return None
    provider_payload = source_payload.get("provider_payload")
    return provider_payload if isinstance(provider_payload, dict) else None


def _load_applied_policy(email_source: EmailSource) -> dict:
    try:
        payload = json.loads(email_source.applied_policy_json or "{}")
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _store_payload(email_source_id: int, attachment_id: int, filename: str, payload: bytes) -> str:
    safe_filename = "".join(char if char.isalnum() or char in ("-", "_", ".") else "_" for char in filename)
    output_dir = Path(STORAGE_INPUT_DIR) / "email" / str(email_source_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{attachment_id}_{safe_filename}"
    path.write_bytes(payload)
    return str(path)
