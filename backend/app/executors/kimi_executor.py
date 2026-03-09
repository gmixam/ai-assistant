from ..models import Task
from .base import ExecutionResult, TaskExecutor
from .provider_config import ProviderConfig


class KimiExecutor(TaskExecutor):
    def __init__(self, config: ProviderConfig):
        self.config = config

    def execute(self, task: Task) -> ExecutionResult:
        return ExecutionResult(
            success=False,
            error_text=(
                "Kimi executor is configured as stub in this stage. "
                "No external API calls are enabled yet."
            ),
        )
