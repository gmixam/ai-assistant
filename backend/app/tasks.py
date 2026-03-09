from datetime import datetime

from pydantic import BaseModel


class TaskCreateRequest(BaseModel):
    input_text: str


class TaskCreateResponse(BaseModel):
    id: str
    task_id: str
    status: str
    created_at: datetime
    updated_at: datetime


class TaskResponse(BaseModel):
    id: str
    input_text: str
    status: str
    created_at: datetime
    updated_at: datetime
