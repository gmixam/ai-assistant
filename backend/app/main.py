import logging
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import Task, TaskAttachment
from .queue import enqueue_task
from .schema import ensure_task_optional_columns
from .tasks import TaskCreateRequest, TaskCreateResponse, TaskResponse


app = FastAPI(title="AI Assistant Backend")
logger = logging.getLogger(__name__)


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
        logger.exception("failed to enqueue task", extra={"task_id": db_task.id})
        # Keep task in "created" so it can be retried/reconciled later.
        raise HTTPException(
            status_code=503,
            detail={"message": "Task created but queue is unavailable", "task_id": db_task.id},
        )

    db_task.status = "queued"
    db.commit()
    db.refresh(db_task)
    attachments = db.query(TaskAttachment).filter(TaskAttachment.task_id == db_task.id).order_by(TaskAttachment.id).all()

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
        "created_at": db_task.created_at,
        "updated_at": db_task.updated_at,
    }


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    attachments = db.query(TaskAttachment).filter(TaskAttachment.task_id == task.id).order_by(TaskAttachment.id).all()
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
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }
