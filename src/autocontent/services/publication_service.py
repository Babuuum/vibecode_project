from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.autocontent.config import Settings
from src.autocontent.integrations.telegram_client import (
    ChannelForbiddenError,
    ChannelNotFoundError,
    TelegramClient,
    TransientTelegramError,
)
from src.autocontent.repos import ChannelBindingRepository, PostDraftRepository, PublicationLogRepository
from src.autocontent.services.quota import NoopQuotaService, QuotaBackend, QuotaExceededError
from src.autocontent.shared.idempotency import IdempotencyStore, InMemoryIdempotencyStore


class PublicationError(Exception):
    pass


PUBLISH_TTL = 24 * 60 * 60  # 24h


class PublicationService:
    def __init__(
        self,
        session: AsyncSession,
        telegram_client: TelegramClient,
        idempotency_store: IdempotencyStore | None = None,
        quota_service: QuotaBackend | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._drafts = PostDraftRepository(session)
        self._logs = PublicationLogRepository(session)
        self._channels = ChannelBindingRepository(session)
        self._session = session
        self._telegram_client = telegram_client
        self._idempotency = idempotency_store or InMemoryIdempotencyStore()
        self._quota = quota_service or NoopQuotaService()
        self._settings = settings or Settings()

    async def publish_draft(self, draft_id: int, max_retries: int = 2) -> PublicationLog:
        key = f"publish:{draft_id}"
        acquired = await self._idempotency.acquire(key, PUBLISH_TTL)
        if not acquired:
            existing = await self._logs.get_by_draft_id(draft_id)
            if existing:
                return existing
            raise PublicationError("Publish already in progress")

        draft = await self._drafts.get_by_id(draft_id)
        if not draft:
            raise PublicationError("Draft not found")

        channel = await self._channels.get_by_project_id(draft.project_id)
        if not channel or channel.status != "connected":
            raise PublicationError("Channel not connected")

        try:
            await self._quota.ensure_can_publish(draft.project_id)
        except QuotaExceededError as exc:
            await self._drafts.update_status(draft.id, "failed")
            await self._logs.create_log(
                draft_id=draft.id,
                status="failed",
                error_code="quota",
                error_text=str(exc),
            )
            raise

        attempt = 0
        last_exc: Exception | None = None
        while attempt <= max_retries:
            try:
                message_id = await self._telegram_client.send_post(channel.channel_id, draft.text)
                draft.status = "published"
                self._session.add(draft)
                log = await self._logs.create_log(
                    draft_id=draft.id,
                    status="published",
                    tg_message_id=message_id,
                    published_at=datetime.now(timezone.utc),
                )
                return log
            except (TransientTelegramError,) as exc:
                last_exc = exc
                attempt += 1
                if attempt > max_retries:
                    break
                await asyncio.sleep(0.5 * attempt)
            except (ChannelForbiddenError, ChannelNotFoundError, PublicationError) as exc:
                await self._drafts.update_status(draft.id, "failed")
                return await self._logs.create_log(
                    draft_id=draft.id,
                    status="failed",
                    error_code=exc.__class__.__name__,
                    error_text=str(exc),
                )

        await self._drafts.update_status(draft.id, "failed")
        return await self._logs.create_log(
            draft_id=draft.id,
            status="failed",
            error_code=last_exc.__class__.__name__ if last_exc else "Unknown",
            error_text=str(last_exc) if last_exc else None,
        )
