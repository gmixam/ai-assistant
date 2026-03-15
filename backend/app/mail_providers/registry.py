from .base import MailProviderAdapter
from .fake import FakeMailProviderAdapter
from .mailru_imap import MailruImapProviderAdapter


class MailProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, MailProviderAdapter] = {
            "mailru_imap": MailruImapProviderAdapter(),
            "fake": FakeMailProviderAdapter(),
        }

    def resolve(self, provider_id: str) -> MailProviderAdapter:
        normalized = provider_id.strip().lower()
        try:
            return self._providers[normalized]
        except KeyError as exc:
            raise KeyError(f"unsupported mail provider: {provider_id}") from exc

    def list_providers(self) -> list[str]:
        return sorted(self._providers.keys())
