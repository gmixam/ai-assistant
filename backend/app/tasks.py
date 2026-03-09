from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TaskCreateRequest(BaseModel):
    input_text: str


class TaskCreateResponse(BaseModel):
    id: str
    task_id: str
    status: str
    result_text: Optional[str] = None
    error_text: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TaskResponse(BaseModel):
    id: str
    input_text: str
    status: str
    result_text: Optional[str] = None
    error_text: Optional[str] = None
    created_at: datetime
    updated_at: datetime
