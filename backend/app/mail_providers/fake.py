import base64
from datetime import datetime
from typing import Any

from ..mail_models import DownloadedMailAttachment, MailFetchBatch, NormalizedMailAttachment, NormalizedMailMessage


class FakeMailProviderAdapter:
    provider_id = "fake"

    def fetch_new_messages(
        self,
        mailbox: str,
        checkpoint: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> MailFetchBatch:
        payload = options or {}
        messages = list(payload.get("messages") or [])
        last_uid = int((checkpoint or {}).get("last_uid") or 0)
        selected = [item for item in messages if int(item.get("uid") or 0) > last_uid]
        limit = payload.get("limit")
        if isinstance(limit, int) and limit > 0:
            selected = selected[:limit]
        next_uid = max([last_uid] + [int(item.get("uid") or 0) for item in selected])
        return MailFetchBatch(raw_messages=selected, next_checkpoint={"last_uid": next_uid})

    def fetch_message(
        self,
        mailbox: str,
        provider_message_id: str,
        options: dict[str, Any] | None = None,
    ) -> Any:
        payload = options or {}
        for item in payload.get("messages") or []:
            if str(item.get("provider_message_id") or item.get("uid")) == str(provider_message_id):
                return item
        raise LookupError(f"fake provider message not found: {provider_message_id}")

    def download_attachment(
        self,
        mailbox: str,
        provider_message_id: str,
        attachment: NormalizedMailAttachment,
        options: dict[str, Any] | None = None,
    ) -> DownloadedMailAttachment:
        provider_payload = attachment.provider_payload or {}
        nested_payload = provider_payload.get("provider_payload") if isinstance(provider_payload.get("provider_payload"), dict) else {}
        encoded = provider_payload.get("content_base64") or nested_payload.get("content_base64")
        if not isinstance(encoded, str) or not encoded.strip():
            raise LookupError(f"fake attachment content is missing: {attachment.attachment_id}")
        payload = base64.b64decode(encoded.encode("utf-8"))
        return DownloadedMailAttachment(
            filename=attachment.filename or f"{attachment.attachment_id}.bin",
            mime_type=attachment.mime_type or "application/octet-stream",
            payload=payload,
        )

    def normalize_message(
        self,
        mailbox: str,
        raw_message: Any,
        options: dict[str, Any] | None = None,
    ) -> NormalizedMailMessage:
        item = dict(raw_message or {})
        attachments = [
            NormalizedMailAttachment(
                attachment_id=str(attachment.get("attachment_id") or attachment.get("provider_attachment_id") or index),
                filename=attachment.get("filename"),
                mime_type=attachment.get("mime_type"),
                file_size=attachment.get("file_size"),
                is_inline=bool(attachment.get("is_inline", False)),
                provider_payload=dict(attachment),
            )
            for index, attachment in enumerate(item.get("attachments") or [], start=1)
        ]
        received_at = item.get("received_at")
        parsed_received_at = None
        if isinstance(received_at, str) and received_at.strip():
            try:
                parsed_received_at = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
            except ValueError:
                parsed_received_at = None
        return NormalizedMailMessage(
            provider=self.provider_id,
            mailbox=mailbox,
            provider_message_id=str(item.get("provider_message_id") or item.get("uid") or ""),
            thread_id=item.get("thread_id"),
            internet_message_id=item.get("internet_message_id"),
            from_address=str(item.get("from_address") or ""),
            from_name=item.get("from_name"),
            subject=item.get("subject"),
            snippet=item.get("snippet"),
            labels=[str(label) for label in item.get("labels") or []],
            attachments=attachments,
            telegram_chat_id=item.get("telegram_chat_id"),
            telegram_user_id=item.get("telegram_user_id"),
            telegram_message_id=item.get("telegram_message_id"),
            reply_to_message_id=item.get("reply_to_message_id"),
            received_at=parsed_received_at,
            provider_payload=item,
        )
