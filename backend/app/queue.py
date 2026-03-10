import logging
import os

from redis import Redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
TASK_QUEUE_NAME = os.getenv("TASK_QUEUE_NAME", "tasks:queue")


def get_redis_client() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True)


def enqueue_task(task_id: str) -> int:
    client = get_redis_client()
    size = client.rpush(TASK_QUEUE_NAME, task_id)
    logger.info("task enqueued", extra={"task_id": task_id, "queue": TASK_QUEUE_NAME, "size": size})
    return int(size)


def dequeue_task(timeout_seconds: int = 5) -> str | None:
    client = get_redis_client()
    item = client.blpop(TASK_QUEUE_NAME, timeout=timeout_seconds)
    if item is None:
        return None
    _, task_id = item
    logger.info("event=task_dequeued task_id=%s queue=%s", task_id, TASK_QUEUE_NAME)
    return task_id
