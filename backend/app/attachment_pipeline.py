import io
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from pypdf import PdfReader
from sqlalchemy.orm import Session

from .models import Task, TaskAttachment

logger = logging.getLogger("attachment_pipeline")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_API_BASE_URL = os.getenv("TELEGRAM_API_BASE_URL", "https://api.telegram.org").rstrip("/")
TELEGRAM_FILE_DOWNLOAD_TIMEOUT_SECONDS = int(os.getenv("TELEGRAM_FILE_DOWNLOAD_TIMEOUT_SECONDS", "30"))
STORAGE_INPUT_DIR = os.getenv("STORAGE_INPUT_DIR", "storage/input")
ATTACHMENT_TEXT_MAX_CHARS = int(os.getenv("ATTACHMENT_TEXT_MAX_CHARS", "50000"))

SUPPORTED_MIME_TYPES = {
    "text/plain",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class AttachmentProcessingError(Exception):
    pass


@dataclass(frozen=True)
class ExtractedAttachment:
    attachment_id: int
    filename: str
    mime_type: str
    local_path: str
    extracted_text: str


def build_execution_input(instruction_text: str, extracted_attachments: list[ExtractedAttachment]) -> str:
    instruction = (instruction_text or "").strip()
    parts: list[str] = [f"Instruction:\n{instruction}"]
    for index, item in enumerate(extracted_attachments, start=1):
        snippet = item.extracted_text[:ATTACHMENT_TEXT_MAX_CHARS]
        parts.append(
            f"Attachment {index} ({item.filename}, {item.mime_type}):\n{snippet}"
        )
    return "\n\n".join(parts).strip()


def prepare_task_execution_input(task: Task, db: Session) -> str:
    attachments = (
        db.query(TaskAttachment)
        .filter(TaskAttachment.task_id == task.id)
        .order_by(TaskAttachment.id)
        .all()
    )
    if not attachments:
        return task.input_text

    extracted: list[ExtractedAttachment] = []
    for attachment in attachments:
        extracted.append(_download_and_extract_attachment(task, attachment, db))

    return build_execution_input(task.input_text, extracted)


def _download_and_extract_attachment(task: Task, attachment: TaskAttachment, db: Session) -> ExtractedAttachment:
    if not TELEGRAM_BOT_TOKEN:
        _mark_attachment_failed(
            attachment,
            db,
            "TELEGRAM_BOT_TOKEN is missing for attachment download.",
        )
        raise AttachmentProcessingError("attachment download is unavailable: TELEGRAM_BOT_TOKEN is missing")

    mime_type = (attachment.mime_type or "").strip().lower()
    if mime_type not in SUPPORTED_MIME_TYPES:
        _mark_attachment_failed(
            attachment,
            db,
            f"unsupported attachment mime_type: {attachment.mime_type}",
        )
        raise AttachmentProcessingError(f"unsupported attachment mime_type: {attachment.mime_type}")

    if not attachment.telegram_file_id:
        _mark_attachment_failed(attachment, db, "telegram_file_id is missing")
        raise AttachmentProcessingError("attachment telegram_file_id is missing")

    attachment.download_status = "downloading"
    attachment.download_error = None
    db.commit()
    db.refresh(attachment)

    try:
        file_path = _telegram_get_file_path(attachment.telegram_file_id)
        payload = _telegram_download_file(file_path)
        local_path = _store_attachment_bytes(task.id, attachment, payload)
        extracted_text = _extract_text(payload, mime_type)
    except AttachmentProcessingError as exc:
        _mark_attachment_failed(attachment, db, str(exc))
        raise
    except Exception as exc:
        message = f"unexpected attachment processing error: {exc}"
        _mark_attachment_failed(attachment, db, message)
        raise AttachmentProcessingError(message) from exc

    if not extracted_text.strip():
        message = f"extracted text is empty for attachment {attachment.filename or attachment.id}"
        _mark_attachment_failed(attachment, db, message)
        raise AttachmentProcessingError(message)

    attachment.local_path = local_path
    attachment.download_status = "downloaded"
    attachment.download_error = None
    db.commit()
    db.refresh(attachment)

    return ExtractedAttachment(
        attachment_id=attachment.id,
        filename=attachment.filename or f"attachment_{attachment.id}",
        mime_type=mime_type,
        local_path=local_path,
        extracted_text=extracted_text,
    )


def _telegram_get_file_path(telegram_file_id: str) -> str:
    params = urllib.parse.urlencode({"file_id": telegram_file_id})
    endpoint = f"{TELEGRAM_API_BASE_URL}/bot{TELEGRAM_BOT_TOKEN}/getFile?{params}"
    request = urllib.request.Request(endpoint, method="GET")

    try:
        with urllib.request.urlopen(request, timeout=TELEGRAM_FILE_DOWNLOAD_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise AttachmentProcessingError(f"Telegram getFile HTTP error: {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise AttachmentProcessingError(f"Telegram getFile network error: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise AttachmentProcessingError("Telegram getFile returned invalid JSON") from exc

    if payload.get("ok") is not True:
        raise AttachmentProcessingError("Telegram getFile returned ok=false")

    result = payload.get("result") if isinstance(payload, dict) else None
    file_path = result.get("file_path") if isinstance(result, dict) else None
    if not file_path:
        raise AttachmentProcessingError("Telegram getFile result does not include file_path")
    return str(file_path)


def _telegram_download_file(file_path: str) -> bytes:
    endpoint = f"{TELEGRAM_API_BASE_URL}/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    request = urllib.request.Request(endpoint, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=TELEGRAM_FILE_DOWNLOAD_TIMEOUT_SECONDS) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise AttachmentProcessingError(f"Telegram file download HTTP error: {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise AttachmentProcessingError(f"Telegram file download network error: {exc.reason}") from exc


def _store_attachment_bytes(task_id: str, attachment: TaskAttachment, payload: bytes) -> str:
    filename = attachment.filename or f"attachment_{attachment.id}"
    safe_filename = _sanitize_filename(filename)
    task_dir = Path(STORAGE_INPUT_DIR) / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    local_path = task_dir / f"{attachment.id}_{safe_filename}"
    local_path.write_bytes(payload)
    return str(local_path)


def _extract_text(payload: bytes, mime_type: str) -> str:
    if mime_type == "text/plain":
        return payload.decode("utf-8", errors="replace")
    if mime_type == "application/pdf":
        return _extract_pdf_text(payload)
    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _extract_docx_text(payload)
    raise AttachmentProcessingError(f"unsupported attachment mime_type: {mime_type}")


def _extract_pdf_text(payload: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(payload))
    except Exception as exc:
        raise AttachmentProcessingError(f"failed to open pdf: {exc}") from exc
    chunks: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            chunks.append(text)
    return "\n".join(chunks)


def _extract_docx_text(payload: bytes) -> str:
    try:
        document = Document(io.BytesIO(payload))
    except Exception as exc:
        raise AttachmentProcessingError(f"failed to open docx: {exc}") from exc
    chunks = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    return "\n".join(chunks)


def _mark_attachment_failed(attachment: TaskAttachment, db: Session, error_text: str) -> None:
    attachment.download_status = "failed"
    attachment.download_error = error_text[:1000]
    db.commit()
    db.refresh(attachment)


def _sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._")
    if not cleaned:
        return "attachment.bin"
    return cleaned[:120]
