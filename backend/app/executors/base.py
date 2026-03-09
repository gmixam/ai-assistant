from dataclasses import dataclass
from typing import Protocol

from ..models import Task


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    result_text: str | None = None
    error_text: str | None = None


class TaskExecutor(Protocol):
    def execute(self, task: Task) -> ExecutionResult:
        ...
