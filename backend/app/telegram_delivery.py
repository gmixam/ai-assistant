import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

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


def deliver_task_to_telegram(task: Task) -> bool:
    if task.telegram_chat_id is None:
        logger.info("telegram delivery skipped: no telegram_chat_id", extra={"task_id": task.id})
        return False
    if not TELEGRAM_BOT_TOKEN:
        logger.info("telegram delivery skipped: TELEGRAM_BOT_TOKEN missing", extra={"task_id": task.id})
        return False

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
        logger.error("Telegram delivery failed (HTTP)", extra={"task_id": task.id, "code": exc.code})
        return False
    except urllib.error.URLError:
        logger.error("Telegram delivery failed (network)", extra={"task_id": task.id})
        return False
    except Exception:
        logger.exception("Telegram delivery failed (unexpected)", extra={"task_id": task.id})
        return False

    if parsed.get("ok") is True:
        logger.info("task delivered to Telegram", extra={"task_id": task.id, "chat_id": task.telegram_chat_id})
        return True

    logger.error("Telegram delivery failed (API response)", extra={"task_id": task.id})
    return False
