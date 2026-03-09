import logging
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import Task
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
    db_task = Task(id=task_id, input_text=task.input_text, status="created")
    db.add(db_task)
    db.commit()
    db.refresh(db_task)

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

    return {
        "id": db_task.id,
        "task_id": db_task.id,
        "status": db_task.status,
        "result_text": db_task.result_text,
        "error_text": db_task.error_text,
        "created_at": db_task.created_at,
        "updated_at": db_task.updated_at,
    }


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "id": task.id,
        "input_text": task.input_text,
        "status": task.status,
        "result_text": task.result_text,
        "error_text": task.error_text,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }
