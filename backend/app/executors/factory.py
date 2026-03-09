import os

from .base import TaskExecutor
from .mock import MockExecutor


def build_executor() -> TaskExecutor:
    executor_kind = os.getenv("TASK_EXECUTOR", "mock").strip().lower()
    if executor_kind == "mock":
        return MockExecutor()
    raise ValueError(f"unsupported TASK_EXECUTOR: {executor_kind}")
