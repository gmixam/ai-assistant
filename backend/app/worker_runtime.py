import argparse
import logging
import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .approval_service import ApprovalCreateData, ApprovalService
from .attachment_pipeline import AttachmentProcessingError
from .agents.router import ExecutionRouter
from .agents.registry import FileAgentRegistry
from .database import Base, SessionLocal, engine
from .executors.base import TaskExecutor
from .executors.factory import build_executor
from .models import Task
from .queue import dequeue_task, enqueue_task
from .schema import ensure_task_optional_columns
from .telegram_delivery import deliver_approval_to_telegram, deliver_task_to_telegram

logger = logging.getLogger("task_worker")
approval_service = ApprovalService()


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
    _log_task_final_structured(task, agent_id=None, team_id=None, failure_category=None)


def _log_task_final_structured(
    task: Task,
    agent_id: str | None,
    team_id: str | None,
    failure_category: str | None,
) -> None:
    resolved_failure_category = failure_category
    if resolved_failure_category is None and task.delivery_status == "failed":
        resolved_failure_category = "delivery_failure"
    logger.info(
        "event=task_finalized task_id=%s team_id=%s agent_id=%s final_status=%s delivery_status=%s failure_category=%s",
        task.id,
        team_id or "none",
        agent_id or "none",
        task.status,
        task.delivery_status or "none",
        resolved_failure_category or "none",
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


def process_task(task_id: str, executor: TaskExecutor, router: ExecutionRouter) -> None:
    db = SessionLocal()
    provider, model = _executor_details(executor)
    resolved_agent_id: str | None = None
    resolved_team_id: str | None = None
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
            resolution = router.resolve(task, db)
            resolved_agent_id = resolution.agent.agent_id
            resolved_team_id = resolution.team.team_id if resolution.team is not None else resolution.agent.team_id
            output = router.route(task, db, executor)
        except AttachmentProcessingError as exc:
            task.status = "failed"
            task.result_text = None
            task.error_text = str(exc)
            db.commit()
            db.refresh(task)
            failure_category = _categorize_attachment_failure(str(exc))
            logger.error(
                "event=attachment_preparation_failed task_id=%s team_id=%s agent_id=%s failure_category=%s error=%s",
                task_id,
                resolved_team_id or "none",
                resolved_agent_id or "none",
                failure_category,
                str(exc),
            )
            _deliver_task_result(task, db)
            _log_task_final_structured(task, resolved_agent_id, resolved_team_id, failure_category)
            return
        except Exception as exc:
            failure_category = _categorize_execution_exception(resolved_agent_id, exc)
            logger.exception(
                "event=agent_routing_failed task_id=%s team_id=%s agent_id=%s failure_category=%s error=%s",
                task_id,
                resolved_team_id or "none",
                resolved_agent_id or "none",
                failure_category,
                exc,
            )
            raise

        if output.success:
            task.status = "done"
            task.result_text = output.result_text
            task.error_text = None
            logger.info(
                "event=agent_execution_succeeded task_id=%s team_id=%s agent_id=%s provider=%s model=%s",
                task_id,
                output.team_id or "none",
                output.agent_id,
                provider,
                model or "none",
            )
        else:
            task.status = "failed"
            task.result_text = None
            task.error_text = output.error_text or "executor reported unsuccessful processing"
            failure_category = _categorize_output_failure(output.agent_id, task.error_text)
            logger.error(
                "event=agent_execution_failed task_id=%s team_id=%s agent_id=%s provider=%s model=%s failure_category=%s error=%s",
                task_id,
                output.team_id or "none",
                output.agent_id,
                provider,
                model or "none",
                failure_category,
                task.error_text,
            )
        db.commit()
        db.refresh(task)
        approval_payload = output.metadata.get("approval_create_data") if isinstance(output.metadata, dict) else None
        if task.status == "done" and isinstance(approval_payload, dict):
            approval_item = approval_service.create_item(
                task,
                ApprovalCreateData(
                    summary=str(approval_payload.get("summary") or "Review generated approval"),
                    proposed_action=approval_payload.get("proposed_action"),
                    structured_result=approval_payload.get("structured_result")
                    if isinstance(approval_payload.get("structured_result"), dict)
                    else None,
                    handoff=approval_payload.get("handoff"),
                ),
                db,
            )
            logger.info("event=approval_created task_id=%s approval_id=%s status=%s", task.id, approval_item.id, approval_item.status)
            if task.telegram_chat_id is not None:
                deliver_approval_to_telegram(task, approval_item)
        suppress_task_delivery = bool(output.metadata.get("suppress_task_delivery")) if isinstance(output.metadata, dict) else False
        if task.status == "done":
            if suppress_task_delivery and task.delivery_status == "pending":
                task.delivery_status = None
                db.commit()
                db.refresh(task)
            if not suppress_task_delivery:
                _deliver_task_result(task, db)
            _log_task_final_structured(task, output.agent_id, output.team_id, None)
        else:
            _deliver_task_result(task, db)
            _log_task_final_structured(task, output.agent_id, output.team_id, _categorize_output_failure(output.agent_id, task.error_text))
    except Exception as exc:
        db.rollback()
        failure_category = _categorize_execution_exception(resolved_agent_id, exc)
        logger.exception(
            "event=worker_task_failed task_id=%s team_id=%s agent_id=%s failure_category=%s error=%s",
            task_id,
            resolved_team_id or "none",
            resolved_agent_id or "none",
            failure_category,
            exc,
        )
        try:
            task = db.get(Task, task_id)
            if task is not None:
                task.status = "failed"
                task.result_text = None
                task.error_text = str(exc)
                db.commit()
                db.refresh(task)
                _log_task_final_structured(task, resolved_agent_id, resolved_team_id, failure_category)
        except Exception:
            db.rollback()
            logger.exception("event=task_failed_persist_error task_id=%s", task_id)
    finally:
        db.close()


def run_worker(max_tasks: int = 0, poll_timeout_seconds: int = 5) -> None:
    Base.metadata.create_all(bind=engine)
    ensure_task_optional_columns(engine)
    executor = build_executor()
    router = ExecutionRouter(FileAgentRegistry())
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

        process_task(task_id, executor, router)
        processed_count += 1

        if max_tasks > 0 and processed_count >= max_tasks:
            logger.info("event=worker_stopped processed_count=%s reason=max_tasks", processed_count)
            return


def _categorize_attachment_failure(error_text: str) -> str:
    text = (error_text or "").lower()
    if "download" in text or "getfile" in text or "telegram_file_id" in text or "network error" in text:
        return "attachment_failure"
    return "extraction_failure"


def _categorize_output_failure(agent_id: str | None, error_text: str | None) -> str:
    if agent_id == "approval_prep_agent":
        return "approval_preparation_failure"
    return "agent_execution_failure"


def _categorize_execution_exception(agent_id: str | None, exc: Exception) -> str:
    if isinstance(exc, AttachmentProcessingError):
        return _categorize_attachment_failure(str(exc))
    if agent_id == "approval_prep_agent":
        return "approval_preparation_failure"
    return "agent_execution_failure"


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
