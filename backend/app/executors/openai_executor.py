import json
import urllib.error
import urllib.request

from ..models import Task
from .base import ExecutionResult, TaskExecutor
from .provider_config import ProviderConfig


class OpenAIExecutor(TaskExecutor):
    def __init__(self, config: ProviderConfig):
        self.config = config

    def execute(self, task: Task) -> ExecutionResult:
        api_key = (self.config.api_key or "").strip()
        if not api_key:
            return ExecutionResult(
                success=False,
                error_text="OpenAI API key is missing (OPENAI_API_KEY).",
            )

        base_url = (self.config.base_url or "https://api.openai.com").rstrip("/")
        endpoint = f"{base_url}/v1/chat/completions"
        model = self.config.model or "gpt-4o-mini"

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": task.input_text}],
            "temperature": 0.2,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            snippet = body[:300] if body else ""
            return ExecutionResult(
                success=False,
                error_text=f"OpenAI HTTP error {exc.code}. {snippet}".strip(),
            )
        except urllib.error.URLError as exc:
            return ExecutionResult(
                success=False,
                error_text=f"OpenAI network error: {exc.reason}",
            )
        except Exception as exc:
            return ExecutionResult(
                success=False,
                error_text=f"OpenAI unexpected error: {exc}",
            )

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return ExecutionResult(success=False, error_text="OpenAI returned non-JSON response.")

        content = self._extract_content(parsed)
        if not content:
            return ExecutionResult(
                success=False,
                error_text="OpenAI response did not contain assistant content.",
            )

        return ExecutionResult(success=True, result_text=content, error_text=None)

    @staticmethod
    def _extract_content(payload: dict) -> str | None:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        first = choices[0] if isinstance(choices[0], dict) else None
        if not first:
            return None
        message = first.get("message")
        if not isinstance(message, dict):
            return None
        content = message.get("content")
        if isinstance(content, str):
            text = content.strip()
            return text or None
        return None
