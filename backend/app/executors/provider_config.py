import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    api_key: str | None
    model: str | None
    timeout_seconds: int
    base_url: str | None = None


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def load_provider_config(provider: str) -> ProviderConfig:
    name = provider.strip().lower()
    if name == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        timeout_seconds = _read_int("OPENAI_TIMEOUT_SECONDS", 30)
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
    elif name == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        timeout_seconds = _read_int("DEEPSEEK_TIMEOUT_SECONDS", 30)
        base_url = os.getenv("DEEPSEEK_BASE_URL")
    elif name == "kimi":
        api_key = os.getenv("KIMI_API_KEY")
        model = os.getenv("KIMI_MODEL", "moonshot-v1-8k")
        timeout_seconds = _read_int("KIMI_TIMEOUT_SECONDS", 30)
        base_url = os.getenv("KIMI_BASE_URL")
    else:
        api_key = None
        model = None
        timeout_seconds = 30
        base_url = None

    return ProviderConfig(
        provider=name,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
        base_url=base_url,
    )
