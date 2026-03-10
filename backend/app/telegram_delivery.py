import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .models import Task

logger = logging.getLogger("telegram_delivery")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_API_BASE_URL = os.getenv("TELEGRAM_API_BASE_URL", "https://api.telegram.org").rstrip("/")
TELEGRAM_DELIVERY_TIMEOUT_SECONDS = int(os.getenv("TELEGRAM_DELIVERY_TIMEOUT_SECONDS", "15"))


def _build_task_message(task: Task) -> str:
    if task.status == "done":
        body = task.result_text or "No result text produced."
        text = f"Task {task.id} completed.\n\n{body}"
    else:
        body = task.error_text or "Unknown execution error."
        text = f"Task {task.id} failed.\n\n{body}"
    if len(text) > 3900:
        return text[:3900] + "\n\n...truncated"
    return text


@dataclass(frozen=True)
class DeliveryOutcome:
    success: bool
    error_text: str | None = None


def deliver_task_to_telegram(task: Task) -> DeliveryOutcome:
    if task.telegram_chat_id is None:
        return DeliveryOutcome(success=False, error_text="telegram_chat_id is missing")
    if not TELEGRAM_BOT_TOKEN:
        return DeliveryOutcome(success=False, error_text="TELEGRAM_BOT_TOKEN is missing")

    logger.info(
        "event=telegram_delivery_started task_id=%s telegram_chat_id=%s delivery_status=%s",
        task.id,
        task.telegram_chat_id,
        task.delivery_status or "pending",
    )

    payload = {
        "chat_id": str(task.telegram_chat_id),
        "text": _build_task_message(task),
    }
    if task.reply_to_message_id is not None:
        payload["reply_to_message_id"] = int(task.reply_to_message_id)

    endpoint = f"{TELEGRAM_API_BASE_URL}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(endpoint, data=data, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=TELEGRAM_DELIVERY_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw)
    except urllib.error.HTTPError as exc:
        logger.error(
            "event=telegram_delivery_failed task_id=%s telegram_chat_id=%s delivery_status=failed error=%s",
            task.id,
            task.telegram_chat_id,
            f"telegram HTTP error {exc.code}",
        )
        return DeliveryOutcome(success=False, error_text=f"telegram HTTP error {exc.code}")
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", "network error")
        logger.error(
            "event=telegram_delivery_failed task_id=%s telegram_chat_id=%s delivery_status=failed error=%s",
            task.id,
            task.telegram_chat_id,
            f"telegram network error: {reason}",
        )
        return DeliveryOutcome(success=False, error_text=f"telegram network error: {reason}")
    except Exception as exc:
        logger.exception(
            "event=telegram_delivery_failed task_id=%s telegram_chat_id=%s delivery_status=failed error=%s",
            task.id,
            task.telegram_chat_id,
            exc,
        )
        return DeliveryOutcome(success=False, error_text=f"telegram unexpected error: {exc}")

    if parsed.get("ok") is True:
        logger.info(
            "event=telegram_delivery_completed task_id=%s telegram_chat_id=%s delivery_status=delivered",
            task.id,
            task.telegram_chat_id,
        )
        return DeliveryOutcome(success=True, error_text=None)

    description = parsed.get("description") if isinstance(parsed, dict) else None
    if isinstance(description, str) and description.strip():
        logger.error(
            "event=telegram_delivery_failed task_id=%s telegram_chat_id=%s delivery_status=failed error=%s",
            task.id,
            task.telegram_chat_id,
            f"telegram API error: {description.strip()}",
        )
        return DeliveryOutcome(success=False, error_text=f"telegram API error: {description.strip()}")
    logger.error(
        "event=telegram_delivery_failed task_id=%s telegram_chat_id=%s delivery_status=failed error=%s",
        task.id,
        task.telegram_chat_id,
        "telegram API returned ok=false",
    )
    return DeliveryOutcome(success=False, error_text="telegram API returned ok=false")
