from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TaskAttachmentCreate(BaseModel):
    telegram_file_id: str
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    telegram_chat_id: Optional[int] = None
    telegram_user_id: Optional[int] = None


class TaskAttachmentResponse(BaseModel):
    id: int
    task_id: str
    telegram_file_id: str
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    telegram_chat_id: Optional[int] = None
    telegram_user_id: Optional[int] = None
    local_path: Optional[str] = None
    download_status: Optional[str] = None
    download_error: Optional[str] = None
    extracted_text_length: Optional[int] = None
    sent_text_length: Optional[int] = None
    was_truncated: Optional[bool] = None
    created_at: datetime


class TaskCreateRequest(BaseModel):
    input_text: str
    attachment: Optional[TaskAttachmentCreate] = None
    telegram_chat_id: Optional[int] = None
    telegram_user_id: Optional[int] = None
    telegram_message_id: Optional[int] = None
    reply_to_message_id: Optional[int] = None


class ApprovalCreateRequest(BaseModel):
    summary: str
    proposed_action: Optional[str] = None
    structured_result: dict | None = None
    handoff: Optional[str] = None
    expires_at: Optional[datetime] = None


class ApprovalDecisionRequest(BaseModel):
    decided_by: Optional[str] = None
    comment: Optional[str] = None


class ApprovalItemResponse(BaseModel):
    id: int
    task_id: str
    status: str
    summary: str
    proposed_action: Optional[str] = None
    structured_result: Optional[str] = None
    handoff: Optional[str] = None
    decision_comment: Optional[str] = None
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


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
    delivery_status: Optional[str] = None
    delivered_at: Optional[datetime] = None
    delivery_error: Optional[str] = None
    attachments: list[TaskAttachmentResponse] = Field(default_factory=list)
    approvals: list[ApprovalItemResponse] = Field(default_factory=list)
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
    delivery_status: Optional[str] = None
    delivered_at: Optional[datetime] = None
    delivery_error: Optional[str] = None
    attachments: list[TaskAttachmentResponse] = Field(default_factory=list)
    approvals: list[ApprovalItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
