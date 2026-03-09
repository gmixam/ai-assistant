from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="AI Assistant Backend")
tasks: dict[str, dict[str, object]] = {}


class TaskRequest(BaseModel):
    input_text: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/tasks")
def create_task(task: TaskRequest):
    task_id = str(uuid4())
    task_data = {
        "id": task_id,
        "text": task.input_text,
        "status": "created",
        "created_at": datetime.now(timezone.utc),
    }
    tasks[task_id] = task_data
    return task_data
