import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class NormalizedMailAttachment:
    attachment_id: str
    filename: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    is_inline: bool = False
    provider_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedMailMessage:
    provider: str
    mailbox: str
    provider_message_id: str
    thread_id: str | None = None
    internet_message_id: str | None = None
    from_address: str = ""
    from_name: str | None = None
    subject: str | None = None
    snippet: str | None = None
    labels: list[str] = field(default_factory=list)
    attachments: list[NormalizedMailAttachment] = field(default_factory=list)
    telegram_chat_id: int | None = None
    telegram_user_id: int | None = None
    telegram_message_id: int | None = None
    reply_to_message_id: int | None = None
    received_at: datetime | None = None
    provider_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MailFetchBatch:
    raw_messages: list[Any]
    next_checkpoint: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DownloadedMailAttachment:
    filename: str
    mime_type: str
    payload: bytes


def dump_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, default=_json_default)


def message_to_json(message: NormalizedMailMessage) -> str:
    return json.dumps(asdict(message), ensure_ascii=True, default=_json_default)


def attachment_to_json(attachment: NormalizedMailAttachment) -> str:
    return json.dumps(asdict(attachment), ensure_ascii=True, default=_json_default)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
