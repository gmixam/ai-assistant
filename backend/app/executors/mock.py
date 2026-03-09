import os
import time

from ..models import Task
from .base import ExecutionResult, TaskExecutor

MOCK_PROCESSING_DELAY_SECONDS = float(os.getenv("MOCK_PROCESSING_DELAY_SECONDS", "0.2"))


class MockExecutor(TaskExecutor):
    def execute(self, task: Task) -> ExecutionResult:
        if MOCK_PROCESSING_DELAY_SECONDS > 0:
            time.sleep(MOCK_PROCESSING_DELAY_SECONDS)

        result_text = f"Mock execution completed for task {task.id}: {task.input_text[:120]}"
        return ExecutionResult(success=True, result_text=result_text, error_text=None)
