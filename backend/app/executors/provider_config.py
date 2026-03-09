import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    api_key: str | None
    model: str | None
    timeout_seconds: int


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
    elif name == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        timeout_seconds = _read_int("DEEPSEEK_TIMEOUT_SECONDS", 30)
    elif name == "kimi":
        api_key = os.getenv("KIMI_API_KEY")
        model = os.getenv("KIMI_MODEL", "moonshot-v1-8k")
        timeout_seconds = _read_int("KIMI_TIMEOUT_SECONDS", 30)
    else:
        api_key = None
        model = None
        timeout_seconds = 30

    return ProviderConfig(provider=name, api_key=api_key, model=model, timeout_seconds=timeout_seconds)
