from typing import Any, Protocol

from ..mail_models import DownloadedMailAttachment, MailFetchBatch, NormalizedMailAttachment, NormalizedMailMessage


class MailProviderAdapter(Protocol):
    provider_id: str

    def fetch_new_messages(
        self,
        mailbox: str,
        checkpoint: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> MailFetchBatch:
        ...

    def fetch_message(
        self,
        mailbox: str,
        provider_message_id: str,
        options: dict[str, Any] | None = None,
    ) -> Any:
        ...

    def download_attachment(
        self,
        mailbox: str,
        provider_message_id: str,
        attachment: NormalizedMailAttachment,
        options: dict[str, Any] | None = None,
    ) -> DownloadedMailAttachment:
        ...

    def normalize_message(
        self,
        mailbox: str,
        raw_message: Any,
        options: dict[str, Any] | None = None,
    ) -> NormalizedMailMessage:
        ...
