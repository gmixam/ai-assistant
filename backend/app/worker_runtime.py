import argparse
import logging
import os
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy.orm import Session

from .attachment_pipeline import AttachmentProcessingError, prepare_task_execution_input
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


def _executor_details(executor: TaskExecutor) -> tuple[str, str | None]:
    provider = getattr(executor, "config", None)
    if provider is not None:
        return (
            str(getattr(provider, "provider", executor.__class__.__name__.lower())),
            getattr(provider, "model", None),
        )
    executor_name = executor.__class__.__name__.removesuffix("Executor").lower()
    return executor_name, None


def _log_task_final(task: Task) -> None:
    logger.info(
        "event=task_finalized task_id=%s final_status=%s delivery_status=%s",
        task.id,
        task.status,
        task.delivery_status or "none",
    )


def _deliver_task_result(task: Task, db: Session) -> None:
    if task.telegram_chat_id is None:
        logger.info("event=telegram_delivery_skipped task_id=%s reason=no_telegram_chat_id", task.id)
        return
    if task.delivery_status == "delivered":
        logger.info("event=telegram_delivery_skipped task_id=%s reason=already_delivered", task.id)
        return
    if task.delivery_status is None:
        task.delivery_status = "pending"
        db.commit()
        db.refresh(task)

    try:
        outcome = deliver_task_to_telegram(task)
    except Exception as exc:
        task.delivery_status = "failed"
        task.delivery_error = f"telegram delivery exception: {exc}"[:1000]
        db.commit()
        db.refresh(task)
        logger.exception("event=telegram_delivery_failed task_id=%s delivery_status=failed error=%s", task.id, exc)
        return

    if outcome.success:
        task.delivery_status = "delivered"
        task.delivered_at = datetime.now(timezone.utc)
        task.delivery_error = None
        db.commit()
        db.refresh(task)
        logger.info("event=telegram_delivery_completed task_id=%s telegram_chat_id=%s delivery_status=%s", task.id, task.telegram_chat_id, task.delivery_status)
        return

    task.delivery_status = "failed"
    task.delivery_error = (outcome.error_text or "telegram delivery failed")[:1000]
    db.commit()
    db.refresh(task)
    logger.error("event=telegram_delivery_failed task_id=%s telegram_chat_id=%s delivery_status=%s error=%s", task.id, task.telegram_chat_id, task.delivery_status, task.delivery_error)


def process_task(task_id: str, executor: TaskExecutor) -> None:
    db = SessionLocal()
    provider, model = _executor_details(executor)
    try:
        task = db.get(Task, task_id)
        if task is None:
            logger.warning("event=task_missing task_id=%s", task_id)
            return

        if task.status != "queued":
            if task.status == "created":
                logger.info("event=task_requeued task_id=%s status=%s reason=created_not_ready", task_id, task.status)
                enqueue_task(task_id)
                return
            logger.info("event=task_skipped task_id=%s status=%s reason=non_queued", task_id, task.status)
            return

        logger.info(
            "event=worker_task_started task_id=%s executor=%s model=%s",
            task_id,
            provider,
            model or "none",
        )
        task.status = "processing"
        task.error_text = None
        db.commit()
        db.refresh(task)

        try:
            execution_input = prepare_task_execution_input(task, db)
        except AttachmentProcessingError as exc:
            task.status = "failed"
            task.result_text = None
            task.error_text = str(exc)
            db.commit()
            db.refresh(task)
            logger.error("event=attachment_preparation_failed task_id=%s error=%s", task_id, str(exc))
            _deliver_task_result(task, db)
            _log_task_final(task)
            return

        execution_task = SimpleNamespace(
            id=task.id,
            input_text=execution_input,
        )
        logger.info(
            "event=ai_execution_started task_id=%s provider=%s model=%s",
            task_id,
            provider,
            model or "none",
        )
        execution = executor.execute(execution_task)

        if execution.success:
            task.status = "done"
            task.result_text = execution.result_text
            task.error_text = None
            logger.info(
                "event=ai_execution_completed task_id=%s provider=%s model=%s final_status=%s",
                task_id,
                provider,
                model or "none",
                task.status,
            )
        else:
            task.status = "failed"
            task.result_text = None
            task.error_text = execution.error_text or "executor reported unsuccessful processing"
            logger.error(
                "event=ai_execution_failed task_id=%s provider=%s model=%s error=%s",
                task_id,
                provider,
                model or "none",
                task.error_text,
            )
        db.commit()
        db.refresh(task)
        if task.status == "done":
            _deliver_task_result(task, db)
            _log_task_final(task)
        else:
            _deliver_task_result(task, db)
            _log_task_final(task)
    except Exception as exc:
        db.rollback()
        logger.exception("event=worker_task_failed task_id=%s error=%s", task_id, exc)
        try:
            task = db.get(Task, task_id)
            if task is not None:
                task.status = "failed"
                task.result_text = None
                task.error_text = str(exc)
                db.commit()
                db.refresh(task)
                _log_task_final(task)
        except Exception:
            db.rollback()
            logger.exception("event=task_failed_persist_error task_id=%s", task_id)
    finally:
        db.close()


def run_worker(max_tasks: int = 0, poll_timeout_seconds: int = 5) -> None:
    Base.metadata.create_all(bind=engine)
    ensure_task_optional_columns(engine)
    executor = build_executor()
    provider, model = _executor_details(executor)
    processed_count = 0
    logger.info(
        "event=worker_started executor=%s model=%s poll_timeout_seconds=%s max_tasks=%s",
        provider,
        model or "none",
        poll_timeout_seconds,
        max_tasks,
    )
    while True:
        task_id = dequeue_task(timeout_seconds=poll_timeout_seconds)
        if task_id is None:
            continue

        process_task(task_id, executor)
        processed_count += 1

        if max_tasks > 0 and processed_count >= max_tasks:
            logger.info("event=worker_stopped processed_count=%s reason=max_tasks", processed_count)
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
