import logging
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from .approval_service import ApprovalCreateData, ApprovalService
from .database import Base, SessionLocal, engine
from .models import ApprovalItem, Task, TaskAttachment
from .queue import enqueue_task
from .schema import ensure_task_optional_columns
from .telegram_delivery import deliver_approval_to_telegram
from .tasks import (
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskResponse,
)


app = FastAPI(title="AI Assistant Backend")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
approval_service = ApprovalService()


@app.on_event("startup")
def on_startup() -> None:
    # MVP-safe schema initialization without destructive operations.
    Base.metadata.create_all(bind=engine)
    ensure_task_optional_columns(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


def _serialize_approval(item: ApprovalItem) -> dict:
    return {
        "id": item.id,
        "task_id": item.task_id,
        "status": item.status,
        "summary": item.summary,
        "proposed_action": item.proposed_action,
        "structured_result": item.structured_result,
        "handoff": item.handoff,
        "decision_comment": item.decision_comment,
        "decided_by": item.decided_by,
        "decided_at": item.decided_at,
        "expires_at": item.expires_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _load_approvals(task_id: str, db: Session) -> list[ApprovalItem]:
    return approval_service.list_for_task(task_id, db)


@app.post("/tasks", response_model=TaskCreateResponse)
def create_task(task: TaskCreateRequest, db: Session = Depends(get_db)):
    task_id = str(uuid4())
    db_task = Task(
        id=task_id,
        input_text=task.input_text,
        status="created",
        telegram_chat_id=task.telegram_chat_id,
        telegram_user_id=task.telegram_user_id,
        telegram_message_id=task.telegram_message_id,
        reply_to_message_id=task.reply_to_message_id,
        delivery_status="pending" if task.telegram_chat_id is not None else None,
        delivered_at=None,
        delivery_error=None,
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    if task.attachment is not None:
        db_attachment = TaskAttachment(
            task_id=db_task.id,
            telegram_file_id=task.attachment.telegram_file_id,
            filename=task.attachment.filename,
            mime_type=task.attachment.mime_type,
            file_size=task.attachment.file_size,
            telegram_chat_id=task.attachment.telegram_chat_id,
            telegram_user_id=task.attachment.telegram_user_id,
            download_status="pending",
        )
        db.add(db_attachment)
        db.commit()

    try:
        enqueue_task(db_task.id)
    except Exception:
        logger.exception("event=intake_failure task_id=%s failure_category=intake_failure", db_task.id)
        # Keep task in "created" so it can be retried/reconciled later.
        raise HTTPException(
            status_code=503,
            detail={"message": "Task created but queue is unavailable", "task_id": db_task.id},
        )

    db_task.status = "queued"
    db.commit()
    db.refresh(db_task)
    attachments = db.query(TaskAttachment).filter(TaskAttachment.task_id == db_task.id).order_by(TaskAttachment.id).all()
    approvals = _load_approvals(db_task.id, db)

    return {
        "id": db_task.id,
        "task_id": db_task.id,
        "status": db_task.status,
        "result_text": db_task.result_text,
        "error_text": db_task.error_text,
        "telegram_chat_id": db_task.telegram_chat_id,
        "telegram_user_id": db_task.telegram_user_id,
        "telegram_message_id": db_task.telegram_message_id,
        "reply_to_message_id": db_task.reply_to_message_id,
        "delivery_status": db_task.delivery_status,
        "delivered_at": db_task.delivered_at,
        "delivery_error": db_task.delivery_error,
        "attachments": [
            {
                "id": attachment.id,
                "task_id": attachment.task_id,
                "telegram_file_id": attachment.telegram_file_id,
                "filename": attachment.filename,
                "mime_type": attachment.mime_type,
                "file_size": attachment.file_size,
                "telegram_chat_id": attachment.telegram_chat_id,
                "telegram_user_id": attachment.telegram_user_id,
                "local_path": attachment.local_path,
                "download_status": attachment.download_status,
                "download_error": attachment.download_error,
                "extracted_text_length": attachment.extracted_text_length,
                "sent_text_length": attachment.sent_text_length,
                "was_truncated": attachment.was_truncated,
                "created_at": attachment.created_at,
            }
            for attachment in attachments
        ],
        "approvals": [_serialize_approval(item) for item in approvals],
        "created_at": db_task.created_at,
        "updated_at": db_task.updated_at,
    }


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    attachments = db.query(TaskAttachment).filter(TaskAttachment.task_id == task.id).order_by(TaskAttachment.id).all()
    approvals = _load_approvals(task.id, db)
    return {
        "id": task.id,
        "input_text": task.input_text,
        "status": task.status,
        "result_text": task.result_text,
        "error_text": task.error_text,
        "telegram_chat_id": task.telegram_chat_id,
        "telegram_user_id": task.telegram_user_id,
        "telegram_message_id": task.telegram_message_id,
        "reply_to_message_id": task.reply_to_message_id,
        "delivery_status": task.delivery_status,
        "delivered_at": task.delivered_at,
        "delivery_error": task.delivery_error,
        "attachments": [
            {
                "id": attachment.id,
                "task_id": attachment.task_id,
                "telegram_file_id": attachment.telegram_file_id,
                "filename": attachment.filename,
                "mime_type": attachment.mime_type,
                "file_size": attachment.file_size,
                "telegram_chat_id": attachment.telegram_chat_id,
                "telegram_user_id": attachment.telegram_user_id,
                "local_path": attachment.local_path,
                "download_status": attachment.download_status,
                "download_error": attachment.download_error,
                "extracted_text_length": attachment.extracted_text_length,
                "sent_text_length": attachment.sent_text_length,
                "was_truncated": attachment.was_truncated,
                "created_at": attachment.created_at,
            }
            for attachment in attachments
        ],
        "approvals": [_serialize_approval(item) for item in approvals],
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


@app.post("/tasks/{task_id}/approvals")
def create_approval(task_id: str, payload: ApprovalCreateRequest, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    item = approval_service.create_item(
        task,
        ApprovalCreateData(
            summary=payload.summary,
            proposed_action=payload.proposed_action,
            structured_result=payload.structured_result,
            handoff=payload.handoff,
            expires_at=payload.expires_at,
        ),
        db,
    )
    logger.info("event=approval_created task_id=%s approval_id=%s status=%s", task.id, item.id, item.status)
    if task.telegram_chat_id is not None:
        deliver_approval_to_telegram(task, item)
    return _serialize_approval(item)


@app.get("/tasks/{task_id}/approvals")
def get_task_approvals(task_id: str, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    items = _load_approvals(task_id, db)
    return {
        "task_id": task_id,
        "approvals": [_serialize_approval(item) for item in items],
    }


@app.get("/approvals/{approval_id}")
def get_approval_item(approval_id: int, db: Session = Depends(get_db)):
    try:
        item = approval_service.get_item(approval_id, db)
    except LookupError:
        raise HTTPException(status_code=404, detail="Approval item not found")
    return _serialize_approval(item)


@app.post("/approvals/{approval_id}/approve")
def approve_item(approval_id: int, payload: ApprovalDecisionRequest, db: Session = Depends(get_db)):
    try:
        decision = approval_service.approve(approval_id, db, decided_by=payload.decided_by, comment=payload.comment)
    except LookupError:
        raise HTTPException(status_code=404, detail="Approval item not found")
    item = decision.item
    logger.info(
        "event=approval_approved task_id=%s approval_id=%s status=%s idempotent=%s",
        item.task_id,
        item.id,
        item.status,
        "false" if decision.changed else "true",
    )
    return _serialize_approval(item)


@app.post("/approvals/{approval_id}/reject")
def reject_item(approval_id: int, payload: ApprovalDecisionRequest, db: Session = Depends(get_db)):
    try:
        decision = approval_service.reject(approval_id, db, decided_by=payload.decided_by, comment=payload.comment)
    except LookupError:
        raise HTTPException(status_code=404, detail="Approval item not found")
    item = decision.item
    logger.info(
        "event=approval_rejected task_id=%s approval_id=%s status=%s idempotent=%s",
        item.task_id,
        item.id,
        item.status,
        "false" if decision.changed else "true",
    )
    return _serialize_approval(item)
