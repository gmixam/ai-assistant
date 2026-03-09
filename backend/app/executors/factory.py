import os

from .base import TaskExecutor
from .deepseek_executor import DeepSeekExecutor
from .kimi_executor import KimiExecutor
from .mock import MockExecutor
from .openai_executor import OpenAIExecutor
from .provider_config import load_provider_config


def build_executor() -> TaskExecutor:
    executor_kind = os.getenv("TASK_EXECUTOR", "mock").strip().lower()
    if executor_kind == "mock":
        return MockExecutor()
    if executor_kind == "openai":
        return OpenAIExecutor(load_provider_config("openai"))
    if executor_kind == "deepseek":
        return DeepSeekExecutor(load_provider_config("deepseek"))
    if executor_kind == "kimi":
        return KimiExecutor(load_provider_config("kimi"))
    raise ValueError(f"unsupported TASK_EXECUTOR: {executor_kind}")
