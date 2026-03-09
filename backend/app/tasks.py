from datetime import datetime

from pydantic import BaseModel


class TaskCreate(BaseModel):
    text: str


class TaskResponse(BaseModel):
    id: str
    text: str
    status: str
    created_at: datetime
