import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .email_intake import persist_normalized_mail_message
from .mail_models import DownloadedMailAttachment, NormalizedMailAttachment, NormalizedMailMessage
from .mail_providers.registry import MailProviderRegistry
from .models import EmailSource, MailboxSyncState

logger = logging.getLogger("mail_sync")


class MailSyncService:
    def __init__(self, registry: MailProviderRegistry | None = None) -> None:
        self._registry = registry or MailProviderRegistry()

    def sync_mailbox(
        self,
        provider: str,
        mailbox: str,
        db: Session,
        provider_options: dict | None = None,
        limit: int | None = None,
    ) -> dict:
        adapter = self._registry.resolve(provider)
        state = self._get_or_create_state(provider, mailbox, db)
        checkpoint = self._load_checkpoint(state)
        effective_options = dict(provider_options or {})
        if limit is not None and "limit" not in effective_options:
            effective_options["limit"] = limit
        logger.info(
            "event=mail_provider_sync_started provider=%s mailbox=%s checkpoint=%s",
            provider,
            mailbox,
            json.dumps(checkpoint, ensure_ascii=True),
        )

        try:
            batch = adapter.fetch_new_messages(mailbox, checkpoint=checkpoint, options=effective_options)
            fetched_count = len(batch.raw_messages)
            normalized_count = 0
            ignore_count = 0
            light_count = 0
            deep_count = 0
            uncertain_count = 0
            duplicate_count = 0
            task_count = 0

            for raw_message in batch.raw_messages:
                provider_message_id = str(raw_message.get("uid") or raw_message.get("provider_message_id") or "")
                logger.info(
                    "event=mail_message_fetched provider=%s mailbox=%s provider_message_id=%s",
                    provider,
                    mailbox,
                    provider_message_id or "unknown",
                )
                normalized = adapter.normalize_message(mailbox, raw_message, options=effective_options)
                normalized_count += 1
                logger.info(
                    "event=mail_message_normalized provider=%s mailbox=%s provider_message_id=%s attachment_count=%s",
                    provider,
                    mailbox,
                    normalized.provider_message_id,
                    len(normalized.attachments),
                )
                email_source = persist_normalized_mail_message(normalized, db)
                if email_source.prefilter_status == "duplicate":
                    duplicate_count += 1
                    logger.info(
                        "event=mail_message_skipped provider=%s mailbox=%s provider_message_id=%s reason=duplicate",
                        provider,
                        mailbox,
                        normalized.provider_message_id,
                    )
                    continue
                if email_source.routing_decision == "ignore":
                    ignore_count += 1
                    logger.info(
                        "event=mail_message_skipped provider=%s mailbox=%s provider_message_id=%s reason=ignore",
                        provider,
                        mailbox,
                        normalized.provider_message_id,
                    )
                    continue
                if email_source.routing_decision == "uncertain":
                    uncertain_count += 1
                    logger.info(
                        "event=mail_message_skipped provider=%s mailbox=%s provider_message_id=%s reason=uncertain",
                        provider,
                        mailbox,
                        normalized.provider_message_id,
                    )
                    continue
                if email_source.routing_decision == "light":
                    light_count += 1
                    logger.info(
                        "event=mail_message_skipped provider=%s mailbox=%s provider_message_id=%s reason=light",
                        provider,
                        mailbox,
                        normalized.provider_message_id,
                    )
                    continue
                deep_count += 1
                if email_source.task_id:
                    task_count += 1

            state.checkpoint_json = json.dumps(batch.next_checkpoint or {}, ensure_ascii=True)
            state.last_status = "completed"
            state.last_error = None
            state.last_synced_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(state)
            logger.info(
                "event=mail_checkpoint_updated provider=%s mailbox=%s checkpoint=%s",
                provider,
                mailbox,
                state.checkpoint_json,
            )
            logger.info(
                "event=mail_provider_sync_completed provider=%s mailbox=%s fetched_count=%s normalized_count=%s task_count=%s",
                provider,
                mailbox,
                fetched_count,
                normalized_count,
                task_count,
            )
            return {
                "provider": provider,
                "mailbox": mailbox,
                "fetched_count": fetched_count,
                "normalized_count": normalized_count,
                "ignore_count": ignore_count,
                "light_count": light_count,
                "deep_count": deep_count,
                "uncertain_count": uncertain_count,
                "duplicate_count": duplicate_count,
                "task_count": task_count,
                "checkpoint": batch.next_checkpoint or {},
            }
        except Exception as exc:
            db.rollback()
            state = self._get_or_create_state(provider, mailbox, db)
            state.last_status = "failed"
            state.last_error = str(exc)[:1000]
            db.commit()
            logger.exception(
                "event=mail_provider_sync_failed provider=%s mailbox=%s error=%s",
                provider,
                mailbox,
                exc,
            )
            raise

    def get_state(self, provider: str, mailbox: str, db: Session) -> MailboxSyncState:
        return self._get_or_create_state(provider, mailbox, db)

    def adapter_registry(self) -> MailProviderRegistry:
        return self._registry

    @staticmethod
    def _get_or_create_state(provider: str, mailbox: str, db: Session) -> MailboxSyncState:
        state = (
            db.query(MailboxSyncState)
            .filter(MailboxSyncState.provider == provider, MailboxSyncState.mailbox == mailbox)
            .order_by(MailboxSyncState.id.asc())
            .first()
        )
        if state is not None:
            return state
        state = MailboxSyncState(provider=provider, mailbox=mailbox, checkpoint_json="{}")
        db.add(state)
        db.commit()
        db.refresh(state)
        return state

    @staticmethod
    def _load_checkpoint(state: MailboxSyncState) -> dict:
        try:
            payload = json.loads(state.checkpoint_json or "{}")
        except (TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}
