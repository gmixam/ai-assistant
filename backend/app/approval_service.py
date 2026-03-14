import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .models import ApprovalItem, Task

APPROVAL_STATUS_PENDING = "pending"
APPROVAL_STATUS_APPROVED = "approved"
APPROVAL_STATUS_REJECTED = "rejected"
APPROVAL_STATUS_EDITED = "edited"
APPROVAL_STATUS_EXPIRED = "expired"

APPROVAL_ALLOWED_STATUSES = {
    APPROVAL_STATUS_PENDING,
    APPROVAL_STATUS_APPROVED,
    APPROVAL_STATUS_REJECTED,
    APPROVAL_STATUS_EDITED,
    APPROVAL_STATUS_EXPIRED,
}


@dataclass(frozen=True)
class ApprovalCreateData:
    summary: str
    proposed_action: str | None = None
    structured_result: dict | None = None
    handoff: str | None = None
    expires_at: datetime | None = None


class ApprovalService:
    def create_item(self, task: Task, payload: ApprovalCreateData, db: Session) -> ApprovalItem:
        item = ApprovalItem(
            task_id=task.id,
            status=APPROVAL_STATUS_PENDING,
            summary=payload.summary,
            proposed_action=payload.proposed_action,
            structured_result=self._dump_json(payload.structured_result),
            handoff=payload.handoff,
            expires_at=payload.expires_at,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def list_for_task(self, task_id: str, db: Session) -> list[ApprovalItem]:
        return db.query(ApprovalItem).filter(ApprovalItem.task_id == task_id).order_by(ApprovalItem.id).all()

    def approve(self, approval_id: int, db: Session, decided_by: str | None = None, comment: str | None = None) -> ApprovalItem:
        item = self._get_item(approval_id, db)
        item.status = APPROVAL_STATUS_APPROVED
        item.decided_by = decided_by
        item.decision_comment = comment
        item.decided_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(item)
        return item

    def reject(self, approval_id: int, db: Session, decided_by: str | None = None, comment: str | None = None) -> ApprovalItem:
        item = self._get_item(approval_id, db)
        item.status = APPROVAL_STATUS_REJECTED
        item.decided_by = decided_by
        item.decision_comment = comment
        item.decided_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def format_for_telegram(item: ApprovalItem) -> str:
        parts = [
            f"Approval {item.id} is {item.status}.",
            "",
            "Proposed action summary:",
            item.summary,
        ]
        if item.proposed_action:
            parts.extend(["", f"Action: {item.proposed_action}"])
        if item.handoff:
            parts.extend(["", f"Handoff: {item.handoff}"])
        return "\n".join(parts)[:3900]

    @staticmethod
    def _get_item(approval_id: int, db: Session) -> ApprovalItem:
        item = db.get(ApprovalItem, approval_id)
        if item is None:
            raise LookupError(f"approval item not found: {approval_id}")
        return item

    @staticmethod
    def _dump_json(payload: dict | None) -> str | None:
        if payload is None:
            return None
        return json.dumps(payload, ensure_ascii=True)
