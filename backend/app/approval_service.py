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


@dataclass(frozen=True)
class ApprovalDecisionResult:
    item: ApprovalItem
    changed: bool


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
        items = db.query(ApprovalItem).filter(ApprovalItem.task_id == task_id).order_by(ApprovalItem.id).all()
        changed = False
        for item in items:
            changed = self._apply_expiration(item) or changed
        if changed:
            db.commit()
            for item in items:
                db.refresh(item)
        return items

    def get_item(self, approval_id: int, db: Session) -> ApprovalItem:
        item = self._get_item(approval_id, db)
        if self._apply_expiration(item):
            db.commit()
            db.refresh(item)
        return item

    def approve(
        self,
        approval_id: int,
        db: Session,
        decided_by: str | None = None,
        comment: str | None = None,
    ) -> ApprovalDecisionResult:
        return self._transition(
            approval_id,
            APPROVAL_STATUS_APPROVED,
            db,
            decided_by=decided_by,
            comment=comment,
        )

    def reject(
        self,
        approval_id: int,
        db: Session,
        decided_by: str | None = None,
        comment: str | None = None,
    ) -> ApprovalDecisionResult:
        return self._transition(
            approval_id,
            APPROVAL_STATUS_REJECTED,
            db,
            decided_by=decided_by,
            comment=comment,
        )

    @staticmethod
    def format_for_telegram(item: ApprovalItem, detailed: bool = False) -> str:
        status_label = ApprovalService.user_facing_status(item.status)
        action_type = ApprovalService.action_type(item)
        suggested_next_step = ApprovalService.suggested_next_step(item)
        parts = [
            f"Approval #{item.id} for task {item.task_id}",
            f"Status: {status_label}",
            "",
            "Summary:",
            item.summary,
            "",
            f"Action type: {action_type}",
            f"Suggested next step: {suggested_next_step}",
        ]
        if item.proposed_action:
            parts.extend(["", f"Proposed action: {item.proposed_action}"])
        if item.handoff:
            parts.extend(["", f"Handoff: {item.handoff}"])
        if detailed:
            if item.structured_result:
                parts.extend(["", "Details:", item.structured_result])
            if item.decision_comment:
                parts.extend(["", f"Decision comment: {item.decision_comment}"])
            if item.decided_by:
                parts.append(f"Decided by: {item.decided_by}")
            if item.decided_at is not None:
                parts.append(f"Decided at: {item.decided_at.isoformat()}")
            if item.expires_at is not None:
                parts.append(f"Expires at: {item.expires_at.isoformat()}")
        return "\n".join(parts)[:3900]

    @staticmethod
    def user_facing_status(status: str) -> str:
        mapping = {
            APPROVAL_STATUS_PENDING: "pending approval",
            APPROVAL_STATUS_APPROVED: "approved",
            APPROVAL_STATUS_REJECTED: "rejected",
            APPROVAL_STATUS_EXPIRED: "expired",
            APPROVAL_STATUS_EDITED: "edited",
        }
        return mapping.get(status, status)

    @staticmethod
    def action_type(item: ApprovalItem) -> str:
        if item.proposed_action:
            return item.proposed_action
        payload = ApprovalService._load_json(item.structured_result)
        if isinstance(payload, dict):
            value = payload.get("action_type") or payload.get("result_type")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "review_action"

    @staticmethod
    def suggested_next_step(item: ApprovalItem) -> str:
        if item.status == APPROVAL_STATUS_PENDING:
            return "Review details on demand, then approve or reject."
        if item.status == APPROVAL_STATUS_APPROVED:
            return "Approval recorded. No external action is executed automatically."
        if item.status == APPROVAL_STATUS_REJECTED:
            return "Rejection recorded. Update the proposal before retrying."
        if item.status == APPROVAL_STATUS_EXPIRED:
            return "Create a new approval item before proceeding."
        return "Review the latest approval state."

    @staticmethod
    def _get_item(approval_id: int, db: Session) -> ApprovalItem:
        item = db.get(ApprovalItem, approval_id)
        if item is None:
            raise LookupError(f"approval item not found: {approval_id}")
        return item

    def _transition(
        self,
        approval_id: int,
        requested_status: str,
        db: Session,
        decided_by: str | None = None,
        comment: str | None = None,
    ) -> ApprovalDecisionResult:
        item = self._get_item(approval_id, db)
        if self._apply_expiration(item):
            db.commit()
            db.refresh(item)
        if item.status != APPROVAL_STATUS_PENDING:
            return ApprovalDecisionResult(item=item, changed=False)

        item.status = requested_status
        item.decided_by = decided_by
        item.decision_comment = comment
        item.decided_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(item)
        return ApprovalDecisionResult(item=item, changed=True)

    @staticmethod
    def _apply_expiration(item: ApprovalItem) -> bool:
        if item.status != APPROVAL_STATUS_PENDING or item.expires_at is None:
            return False
        expires_at = item.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            item.status = APPROVAL_STATUS_EXPIRED
            item.updated_at = datetime.now(timezone.utc)
            return True
        return False

    @staticmethod
    def _dump_json(payload: dict | None) -> str | None:
        if payload is None:
            return None
        return json.dumps(payload, ensure_ascii=True)

    @staticmethod
    def _load_json(payload: str | None) -> dict | None:
        if not payload:
            return None
        try:
            parsed = json.loads(payload)
        except (TypeError, ValueError):
            return None
        if isinstance(parsed, dict):
            return parsed
        return None
