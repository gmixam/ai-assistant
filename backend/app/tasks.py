from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TaskCreateRequest(BaseModel):
    input_text: str
    telegram_chat_id: Optional[int] = None
    telegram_user_id: Optional[int] = None
    telegram_message_id: Optional[int] = None
    reply_to_message_id: Optional[int] = None


class TaskCreateResponse(BaseModel):
    id: str
    task_id: str
    status: str
    result_text: Optional[str] = None
    error_text: Optional[str] = None
    telegram_chat_id: Optional[int] = None
    telegram_user_id: Optional[int] = None
    telegram_message_id: Optional[int] = None
    reply_to_message_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class TaskResponse(BaseModel):
    id: str
    input_text: str
    status: str
    result_text: Optional[str] = None
    error_text: Optional[str] = None
    telegram_chat_id: Optional[int] = None
    telegram_user_id: Optional[int] = None
    telegram_message_id: Optional[int] = None
    reply_to_message_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
