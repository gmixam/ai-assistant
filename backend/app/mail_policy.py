import json
import logging
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy.orm import Session

from .mail_models import NormalizedMailMessage
from .models import EmailSource, MailRoutingOverride, MailboxPolicy, Task

logger = logging.getLogger("mail_policy")

ROLLOUT_OBSERVE_ONLY = "observe_only"
ROLLOUT_APPROVAL_ONLY_FOR_DEEP = "approval_only_for_deep"
ROLLOUT_FULL_MODE = "full_mode"
SUPPORTED_ROLLOUT_MODES = {
    ROLLOUT_OBSERVE_ONLY,
    ROLLOUT_APPROVAL_ONLY_FOR_DEEP,
    ROLLOUT_FULL_MODE,
}


@dataclass(frozen=True)
class MailPolicySettings:
    scope_mode: str
    scope_values: list[str]
    trusted_senders: list[str]
    trusted_domains: list[str]
    blocked_senders: list[str]
    blocked_domains: list[str]
    watch_senders: list[str]
    watch_domains: list[str]
    priority_rules: list[dict]
    triage_thresholds: dict
    attachment_policy: dict
    rollout_mode: str


@dataclass(frozen=True)
class PolicyDecision:
    routing_decision: str
    triage_score: int
    reason_codes: list[str]
    rule_hits: list[str]
    decision_source: str
    rollout_mode: str
    uncertain_reason: str | None
    create_deep_task: bool
    attachment_download_allowed: bool
    applied_policy: dict


def load_mailbox_policy(provider: str, mailbox: str, db: Session) -> MailPolicySettings:
    record = (
        db.query(MailboxPolicy)
        .filter(MailboxPolicy.provider == provider, MailboxPolicy.mailbox == mailbox)
        .order_by(MailboxPolicy.id.asc())
        .first()
    )
    if record is None:
        return MailPolicySettings(
            scope_mode="all",
            scope_values=[],
            trusted_senders=[],
            trusted_domains=[],
            blocked_senders=[],
            blocked_domains=[],
            watch_senders=[],
            watch_domains=[],
            priority_rules=[],
            triage_thresholds={"light_min": 25, "deep_min": 60, "deep_with_attachment_min": 40, "uncertain_band": 5},
            attachment_policy={"download_for": ["deep"], "max_attachments": 10},
            rollout_mode=ROLLOUT_APPROVAL_ONLY_FOR_DEEP,
        )
    return MailPolicySettings(
        scope_mode=record.scope_mode,
        scope_values=_load_json_list(record.scope_values_json),
        trusted_senders=_load_json_list(record.trusted_senders_json),
        trusted_domains=_load_json_list(record.trusted_domains_json),
        blocked_senders=_load_json_list(record.blocked_senders_json),
        blocked_domains=_load_json_list(record.blocked_domains_json),
        watch_senders=_load_json_list(record.watch_senders_json),
        watch_domains=_load_json_list(record.watch_domains_json),
        priority_rules=_load_json_list(record.priority_rules_json),
        triage_thresholds=_load_json_dict(record.triage_thresholds_json),
        attachment_policy=_load_json_dict(record.attachment_policy_json),
        rollout_mode=record.rollout_mode,
    )


def upsert_mailbox_policy(provider: str, mailbox: str, payload: dict, db: Session) -> MailboxPolicy:
    record = (
        db.query(MailboxPolicy)
        .filter(MailboxPolicy.provider == provider, MailboxPolicy.mailbox == mailbox)
        .order_by(MailboxPolicy.id.asc())
        .first()
    )
    if record is None:
        record = MailboxPolicy(provider=provider, mailbox=mailbox)
        db.add(record)
        db.flush()
    record.scope_mode = str(payload.get("scope_mode") or "all")
    record.scope_values_json = json.dumps(payload.get("scope_values") or [], ensure_ascii=True)
    record.trusted_senders_json = json.dumps(payload.get("trusted_senders") or [], ensure_ascii=True)
    record.trusted_domains_json = json.dumps(payload.get("trusted_domains") or [], ensure_ascii=True)
    record.blocked_senders_json = json.dumps(payload.get("blocked_senders") or [], ensure_ascii=True)
    record.blocked_domains_json = json.dumps(payload.get("blocked_domains") or [], ensure_ascii=True)
    record.watch_senders_json = json.dumps(payload.get("watch_senders") or [], ensure_ascii=True)
    record.watch_domains_json = json.dumps(payload.get("watch_domains") or [], ensure_ascii=True)
    record.priority_rules_json = json.dumps(payload.get("priority_rules") or [], ensure_ascii=True)
    record.triage_thresholds_json = json.dumps(payload.get("triage_thresholds") or {}, ensure_ascii=True)
    record.attachment_policy_json = json.dumps(payload.get("attachment_policy") or {}, ensure_ascii=True)
    rollout_mode = str(payload.get("rollout_mode") or ROLLOUT_APPROVAL_ONLY_FOR_DEEP)
    record.rollout_mode = rollout_mode if rollout_mode in SUPPORTED_ROLLOUT_MODES else ROLLOUT_APPROVAL_ONLY_FOR_DEEP
    db.commit()
    db.refresh(record)
    return record


def serialize_mailbox_policy(provider: str, mailbox: str, db: Session) -> dict:
    settings = load_mailbox_policy(provider, mailbox, db)
    return {
        "provider": provider,
        "mailbox": mailbox,
        "scope_mode": settings.scope_mode,
        "scope_values": settings.scope_values,
        "trusted_senders": settings.trusted_senders,
        "trusted_domains": settings.trusted_domains,
        "blocked_senders": settings.blocked_senders,
        "blocked_domains": settings.blocked_domains,
        "watch_senders": settings.watch_senders,
        "watch_domains": settings.watch_domains,
        "priority_rules": settings.priority_rules,
        "triage_thresholds": settings.triage_thresholds,
        "attachment_policy": settings.attachment_policy,
        "rollout_mode": settings.rollout_mode,
    }


def apply_policy(
    message: NormalizedMailMessage,
    base_prefilter_status: str,
    base_score: int,
    base_decision: str,
    base_reason_codes: list[str],
    policy: MailPolicySettings,
) -> PolicyDecision:
    sender = (message.from_address or "").strip().lower()
    domain = sender.split("@", 1)[1] if "@" in sender else ""
    labels = {str(item).strip().lower() for item in message.labels}
    rule_hits: list[str] = []
    reason_codes = list(base_reason_codes)
    score = int(base_score)
    routing_decision = base_decision
    decision_source = "base_triage"
    uncertain_reason = None

    if policy.scope_mode == "labels_include" and policy.scope_values:
        if not labels.intersection({item.lower() for item in policy.scope_values}):
            rule_hits.append("scope_excluded")
            reason_codes.append("policy_scope_excluded")
            routing_decision = "ignore"
            decision_source = "policy_scope"
    if sender in {item.lower() for item in policy.blocked_senders}:
        rule_hits.append("blocked_sender")
        reason_codes.append("policy_blocked_sender")
        routing_decision = "ignore"
        decision_source = "policy_blocked"
    if domain and domain in {item.lower() for item in policy.blocked_domains}:
        rule_hits.append("blocked_domain")
        reason_codes.append("policy_blocked_domain")
        routing_decision = "ignore"
        decision_source = "policy_blocked"

    if sender in {item.lower() for item in policy.trusted_senders}:
        score += 20
        rule_hits.append("trusted_sender")
        reason_codes.append("policy_trusted_sender")
    if domain and domain in {item.lower() for item in policy.trusted_domains}:
        score += 15
        rule_hits.append("trusted_domain")
        reason_codes.append("policy_trusted_domain")

    if sender in {item.lower() for item in policy.watch_senders}:
        rule_hits.append("watch_sender")
        reason_codes.append("policy_watch_sender")
        uncertain_reason = "watch_sender_requires_review"
    if domain and domain in {item.lower() for item in policy.watch_domains}:
        rule_hits.append("watch_domain")
        reason_codes.append("policy_watch_domain")
        uncertain_reason = uncertain_reason or "watch_domain_requires_review"

    for priority_rule in policy.priority_rules:
        pattern = str(priority_rule.get("contains") or "").strip().lower()
        boost = int(priority_rule.get("boost") or 0)
        text = f"{message.subject or ''}\n{message.snippet or ''}".lower()
        if pattern and pattern in text:
            score += boost
            hit = f"priority:{pattern}"
            rule_hits.append(hit)
            reason_codes.append("policy_priority_rule")

    thresholds = {
        "light_min": int(policy.triage_thresholds.get("light_min", 25)),
        "deep_min": int(policy.triage_thresholds.get("deep_min", 60)),
        "deep_with_attachment_min": int(policy.triage_thresholds.get("deep_with_attachment_min", 40)),
        "uncertain_band": int(policy.triage_thresholds.get("uncertain_band", 5)),
    }
    score = max(0, min(score, 100))
    if routing_decision != "ignore":
        if score >= thresholds["deep_min"] or (message.attachments and score >= thresholds["deep_with_attachment_min"]):
            routing_decision = "deep"
            decision_source = "policy_thresholds"
        elif score >= thresholds["light_min"]:
            routing_decision = "light"
            decision_source = "policy_thresholds"
        else:
            routing_decision = "ignore"
            decision_source = "policy_thresholds"

    if uncertain_reason is None:
        if abs(score - thresholds["deep_min"]) <= thresholds["uncertain_band"]:
            uncertain_reason = "near_deep_threshold"
        elif abs(score - thresholds["light_min"]) <= thresholds["uncertain_band"]:
            uncertain_reason = "near_light_threshold"
    if uncertain_reason is not None and routing_decision != "ignore":
        routing_decision = "uncertain"
        decision_source = "policy_uncertain"
        reason_codes.append("policy_uncertain_review")
        rule_hits.append(f"uncertain:{uncertain_reason}")

    create_deep_task = routing_decision == "deep"
    if policy.rollout_mode == ROLLOUT_OBSERVE_ONLY:
        create_deep_task = False
        reason_codes.append("policy_rollout_observe_only")
        rule_hits.append("rollout:observe_only")
        if routing_decision == "deep":
            decision_source = "rollout_mode"
    elif policy.rollout_mode == ROLLOUT_APPROVAL_ONLY_FOR_DEEP:
        rule_hits.append("rollout:approval_only_for_deep")
    elif policy.rollout_mode == ROLLOUT_FULL_MODE:
        rule_hits.append("rollout:full_mode")

    attachment_policy = {"download_for": ["deep"], "max_attachments": 10}
    attachment_policy.update(policy.attachment_policy)
    attachment_download_allowed = routing_decision in set(attachment_policy.get("download_for") or ["deep"])

    logger.info(
        "event=mail_policy_applied provider=%s mailbox=%s provider_message_id=%s decision=%s decision_source=%s rollout_mode=%s score=%s",
        message.provider,
        message.mailbox,
        message.provider_message_id,
        routing_decision,
        decision_source,
        policy.rollout_mode,
        score,
    )

    return PolicyDecision(
        routing_decision=routing_decision,
        triage_score=score,
        reason_codes=reason_codes,
        rule_hits=rule_hits,
        decision_source=decision_source,
        rollout_mode=policy.rollout_mode,
        uncertain_reason=uncertain_reason,
        create_deep_task=create_deep_task,
        attachment_download_allowed=attachment_download_allowed,
        applied_policy={
            "scope_mode": policy.scope_mode,
            "scope_values": policy.scope_values,
            "triage_thresholds": thresholds,
            "attachment_policy": attachment_policy,
            "rollout_mode": policy.rollout_mode,
        },
    )


def apply_manual_override(
    email_source: EmailSource,
    to_decision: str,
    db: Session,
    decided_by: str | None = None,
    comment: str | None = None,
) -> MailRoutingOverride:
    from_decision = email_source.routing_decision
    override = MailRoutingOverride(
        email_source_id=email_source.id,
        from_decision=from_decision,
        to_decision=to_decision,
        decided_by=decided_by,
        comment=comment,
    )
    db.add(override)
    email_source.routing_decision = to_decision
    email_source.decision_source = "manual_override"
    try:
        reason_codes = json.loads(email_source.reason_codes_json or "[]")
    except (TypeError, ValueError):
        reason_codes = []
    try:
        rule_hits = json.loads(email_source.rule_hits_json or "[]")
    except (TypeError, ValueError):
        rule_hits = []
    reason_codes.append(f"manual_override:{from_decision}->{to_decision}")
    rule_hits.append(f"override:{from_decision}->{to_decision}")
    email_source.reason_codes_json = json.dumps(reason_codes, ensure_ascii=True)
    email_source.rule_hits_json = json.dumps(rule_hits, ensure_ascii=True)
    db.commit()
    db.refresh(override)
    db.refresh(email_source)
    logger.info(
        "event=mail_manual_override_applied email_source_id=%s from_decision=%s to_decision=%s decided_by=%s",
        email_source.id,
        from_decision,
        to_decision,
        decided_by or "unknown",
    )
    return override


def maybe_create_override_task(email_source: EmailSource, message: NormalizedMailMessage, db: Session) -> Task | None:
    if email_source.routing_decision != "deep" or email_source.task_id is not None:
        return None
    task = Task(
        id=str(uuid4()),
        input_text=(
            "Email deep triage\n"
            f"provider={email_source.provider}\n"
            f"mailbox={email_source.mailbox}\n"
            f"email_source_id={email_source.id}\n"
            f"from={message.from_address}\n"
            f"subject={message.subject or '(no subject)'}\n"
            f"snippet={message.snippet or ''}\n"
            f"attachments={', '.join([item.filename or item.mime_type or 'unknown' for item in message.attachments]) or 'none'}"
        ),
        status="created",
        telegram_chat_id=message.telegram_chat_id,
        telegram_user_id=message.telegram_user_id,
        telegram_message_id=message.telegram_message_id,
        reply_to_message_id=message.reply_to_message_id,
        delivery_status="pending" if message.telegram_chat_id is not None else None,
    )
    db.add(task)
    db.flush()
    from .queue import enqueue_task

    enqueue_task(task.id)
    task.status = "queued"
    email_source.task_id = task.id
    db.commit()
    db.refresh(task)
    db.refresh(email_source)
    return task


def _load_json_list(value: str | None) -> list:
    try:
        payload = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return payload if isinstance(payload, list) else []


def _load_json_dict(value: str | None) -> dict:
    try:
        payload = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}
