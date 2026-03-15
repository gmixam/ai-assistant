import email
import imaplib
import os
import re
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

from ..mail_models import DownloadedMailAttachment, MailFetchBatch, NormalizedMailAttachment, NormalizedMailMessage


class MailruImapProviderAdapter:
    provider_id = "mailru_imap"

    def __init__(self) -> None:
        self._host = os.getenv("MAILRU_IMAP_HOST", "imap.mail.ru").strip()
        self._port = int(os.getenv("MAILRU_IMAP_PORT", "993"))
        self._username = os.getenv("MAILRU_IMAP_USERNAME", "").strip()
        self._password = os.getenv("MAILRU_IMAP_PASSWORD", "").strip()
        self._folder = os.getenv("MAILRU_IMAP_FOLDER", "INBOX").strip() or "INBOX"

    def fetch_new_messages(
        self,
        mailbox: str,
        checkpoint: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> MailFetchBatch:
        last_uid = int((checkpoint or {}).get("last_uid") or 0)
        folder = str((options or {}).get("folder") or self._folder)
        client = self._connect()
        try:
            self._select_mailbox(client, folder)
            status, data = client.uid("SEARCH", None, "ALL")
            if status != "OK":
                raise RuntimeError("Mail.ru IMAP search failed")
            all_uids = [int(item) for item in (data[0] or b"").split() if item]
            selected_uids = [uid for uid in all_uids if uid > last_uid]
            limit = (options or {}).get("limit")
            if isinstance(limit, int) and limit > 0:
                selected_uids = selected_uids[:limit]
            raw_messages: list[dict[str, Any]] = []
            for uid in selected_uids:
                status, payload = client.uid("FETCH", str(uid), "(RFC822 FLAGS)")
                if status != "OK" or not payload:
                    continue
                raw_bytes = self._extract_rfc822_bytes(payload)
                if raw_bytes is None:
                    continue
                raw_messages.append({"uid": uid, "folder": folder, "rfc822": raw_bytes})
            next_uid = max([last_uid] + selected_uids)
            return MailFetchBatch(raw_messages=raw_messages, next_checkpoint={"last_uid": next_uid, "folder": folder})
        finally:
            self._close(client)

    def fetch_message(
        self,
        mailbox: str,
        provider_message_id: str,
        options: dict[str, Any] | None = None,
    ) -> Any:
        folder = str((options or {}).get("folder") or self._folder)
        client = self._connect()
        try:
            self._select_mailbox(client, folder)
            status, payload = client.uid("FETCH", provider_message_id, "(RFC822 FLAGS)")
            if status != "OK" or not payload:
                raise LookupError(f"Mail.ru IMAP message not found: {provider_message_id}")
            raw_bytes = self._extract_rfc822_bytes(payload)
            if raw_bytes is None:
                raise LookupError(f"Mail.ru IMAP message payload missing: {provider_message_id}")
            return {"uid": int(provider_message_id), "folder": folder, "rfc822": raw_bytes}
        finally:
            self._close(client)

    def download_attachment(
        self,
        mailbox: str,
        provider_message_id: str,
        attachment: NormalizedMailAttachment,
        options: dict[str, Any] | None = None,
    ) -> DownloadedMailAttachment:
        raw_message = self.fetch_message(mailbox, provider_message_id, options=options)
        parsed = email.message_from_bytes(raw_message["rfc822"])
        target_part = self._resolve_part(parsed, str(attachment.provider_payload.get("part_path") or attachment.attachment_id))
        if target_part is None:
            raise LookupError(f"Mail.ru IMAP attachment not found: {attachment.attachment_id}")
        payload = target_part.get_payload(decode=True) or b""
        filename = self._decode_header(target_part.get_filename()) or attachment.filename or f"{attachment.attachment_id}.bin"
        mime_type = target_part.get_content_type() or attachment.mime_type or "application/octet-stream"
        return DownloadedMailAttachment(filename=filename, mime_type=mime_type, payload=payload)

    def normalize_message(
        self,
        mailbox: str,
        raw_message: Any,
        options: dict[str, Any] | None = None,
    ) -> NormalizedMailMessage:
        raw_bytes = raw_message.get("rfc822")
        if not isinstance(raw_bytes, (bytes, bytearray)):
            raise ValueError("Mail.ru IMAP raw message does not include RFC822 bytes")
        parsed = email.message_from_bytes(raw_bytes)
        sender_name, sender_address = self._parse_sender(parsed.get("From"))
        subject = self._decode_header(parsed.get("Subject"))
        received_at = self._parse_received_at(parsed.get("Date"))
        snippet = self._extract_snippet(parsed)
        attachments = self._extract_attachments(parsed)
        flags = []
        return NormalizedMailMessage(
            provider=self.provider_id,
            mailbox=mailbox,
            provider_message_id=str(raw_message.get("uid") or ""),
            thread_id=parsed.get("Thread-Index"),
            internet_message_id=parsed.get("Message-ID"),
            from_address=sender_address,
            from_name=sender_name,
            subject=subject,
            snippet=snippet,
            labels=flags,
            attachments=attachments,
            received_at=received_at,
            provider_payload={"folder": raw_message.get("folder") or self._folder},
        )

    def _connect(self) -> imaplib.IMAP4_SSL:
        if not self._username or not self._password:
            raise RuntimeError("MAILRU_IMAP_USERNAME and MAILRU_IMAP_PASSWORD are required")
        client = imaplib.IMAP4_SSL(self._host, self._port)
        client.login(self._username, self._password)
        return client

    @staticmethod
    def _close(client: imaplib.IMAP4_SSL) -> None:
        try:
            client.logout()
        except Exception:
            pass

    @staticmethod
    def _select_mailbox(client: imaplib.IMAP4_SSL, folder: str) -> None:
        status, _ = client.select(folder, readonly=True)
        if status != "OK":
            raise RuntimeError(f"Mail.ru IMAP select failed for folder {folder}")

    @staticmethod
    def _extract_rfc822_bytes(payload: list[Any]) -> bytes | None:
        for item in payload:
            if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
                return bytes(item[1])
        return None

    @staticmethod
    def _decode_header(value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return str(make_header(decode_header(value))).strip() or None
        except Exception:
            return value.strip() or None

    def _parse_sender(self, header_value: str | None) -> tuple[str | None, str]:
        parsed = getaddresses([header_value or ""])
        if not parsed:
            return None, ""
        name, address = parsed[0]
        return (self._decode_header(name), address.strip())

    @staticmethod
    def _parse_received_at(header_value: str | None):
        if not header_value:
            return None
        try:
            return parsedate_to_datetime(header_value)
        except (TypeError, ValueError, IndexError):
            return None

    def _extract_snippet(self, parsed: Message) -> str:
        text = ""
        if parsed.is_multipart():
            for part in parsed.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                disposition = (part.get("Content-Disposition") or "").lower()
                if "attachment" in disposition:
                    continue
                content_type = part.get_content_type()
                payload = part.get_payload(decode=True) or b""
                if content_type == "text/plain":
                    charset = part.get_content_charset() or "utf-8"
                    text = payload.decode(charset, "ignore")
                    break
                if not text and content_type == "text/html":
                    charset = part.get_content_charset() or "utf-8"
                    html = payload.decode(charset, "ignore")
                    text = re.sub(r"<[^>]+>", " ", html)
        else:
            payload = parsed.get_payload(decode=True) or b""
            charset = parsed.get_content_charset() or "utf-8"
            text = payload.decode(charset, "ignore")
        return " ".join(text.split())[:280] or None

    def _extract_attachments(self, parsed: Message) -> list[NormalizedMailAttachment]:
        attachments: list[NormalizedMailAttachment] = []
        for part_path, part in self._walk_with_part_paths(parsed):
            filename = self._decode_header(part.get_filename())
            disposition = (part.get("Content-Disposition") or "").lower()
            if not filename and "attachment" not in disposition:
                continue
            attachments.append(
                NormalizedMailAttachment(
                    attachment_id=part_path,
                    filename=filename,
                    mime_type=part.get_content_type(),
                    file_size=len(part.get_payload(decode=True) or b""),
                    is_inline="inline" in disposition,
                    provider_payload={"part_path": part_path},
                )
            )
        return attachments

    def _walk_with_part_paths(self, parsed: Message) -> list[tuple[str, Message]]:
        collected: list[tuple[str, Message]] = []

        def visit(part: Message, prefix: str = "") -> None:
            if part.is_multipart():
                for index, child in enumerate(part.get_payload() or [], start=1):
                    child_prefix = f"{prefix}.{index}" if prefix else str(index)
                    visit(child, child_prefix)
                return
            collected.append((prefix or "1", part))

        visit(parsed)
        return collected

    def _resolve_part(self, parsed: Message, part_path: str) -> Message | None:
        for candidate_path, part in self._walk_with_part_paths(parsed):
            if candidate_path == part_path:
                return part
        return None
