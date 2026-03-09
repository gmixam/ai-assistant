import argparse
import logging
import os

from .database import Base, SessionLocal, engine
from .executors.base import TaskExecutor
from .executors.factory import build_executor
from .models import Task
from .queue import dequeue_task, enqueue_task
from .schema import ensure_task_optional_columns
from .telegram_delivery import deliver_task_to_telegram

logger = logging.getLogger("task_worker")


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("WORKER_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def process_task(task_id: str, executor: TaskExecutor) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task is None:
            logger.warning("task not found in PostgreSQL", extra={"task_id": task_id})
            return

        if task.status != "queued":
            if task.status == "created":
                logger.info("task not ready yet, requeue", extra={"task_id": task_id, "status": task.status})
                enqueue_task(task_id)
                return
            logger.info(
                "task skipped due to non-queued status",
                extra={"task_id": task_id, "status": task.status},
            )
            return

        logger.info("processing started", extra={"task_id": task_id})
        task.status = "processing"
        task.error_text = None
        db.commit()
        db.refresh(task)

        execution = executor.execute(task)

        if execution.success:
            task.status = "done"
            task.result_text = execution.result_text
            task.error_text = None
        else:
            task.status = "failed"
            task.result_text = None
            task.error_text = execution.error_text or "executor reported unsuccessful processing"
        db.commit()
        db.refresh(task)
        if task.status == "done":
            logger.info("processing completed", extra={"task_id": task_id, "status": task.status})
            if not deliver_task_to_telegram(task):
                logger.info("task done without Telegram delivery", extra={"task_id": task_id})
        else:
            logger.error("processing failed", extra={"task_id": task_id, "status": task.status})
            if not deliver_task_to_telegram(task):
                logger.info("task failed without Telegram delivery", extra={"task_id": task_id})
    except Exception as exc:
        db.rollback()
        logger.exception("processing failed", extra={"task_id": task_id})
        try:
            task = db.get(Task, task_id)
            if task is not None:
                task.status = "failed"
                task.result_text = None
                task.error_text = str(exc)
                db.commit()
                db.refresh(task)
                logger.info("task marked as failed", extra={"task_id": task_id})
        except Exception:
            db.rollback()
            logger.exception("failed to persist failed status", extra={"task_id": task_id})
    finally:
        db.close()


def run_worker(max_tasks: int = 0, poll_timeout_seconds: int = 5) -> None:
    Base.metadata.create_all(bind=engine)
    ensure_task_optional_columns(engine)
    executor = build_executor()
    processed_count = 0
    logger.info("worker started")
    while True:
        task_id = dequeue_task(timeout_seconds=poll_timeout_seconds)
        if task_id is None:
            continue

        logger.info("task picked", extra={"task_id": task_id})
        process_task(task_id, executor)
        processed_count += 1

        if max_tasks > 0 and processed_count >= max_tasks:
            logger.info("worker exiting after max_tasks", extra={"processed_count": processed_count})
            return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Minimal task worker runtime")
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=0,
        help="Stop after processing N queue items (0 = run forever)",
    )
    parser.add_argument(
        "--poll-timeout",
        type=int,
        default=5,
        help="BLPOP timeout in seconds",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    run_worker(max_tasks=args.max_tasks, poll_timeout_seconds=args.poll_timeout)


if __name__ == "__main__":
    main()
