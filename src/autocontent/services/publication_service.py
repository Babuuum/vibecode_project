from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.config import Settings
from autocontent.integrations.telegram_client import (
    ChannelForbiddenError,
    ChannelNotFoundError,
    TelegramClient,
    TransientTelegramError,
)
from autocontent.repos import (
    ChannelBindingRepository,
    PostDraftRepository,
    PublicationLogRepository,
    ScheduleRepository,
    UsageCounterRepository,
)
from autocontent.services.quota import NoopQuotaService, QuotaBackend, QuotaExceededError
from autocontent.shared.idempotency import IdempotencyStore, InMemoryIdempotencyStore


class PublicationError(Exception):
    pass


PUBLISH_TTL = 24 * 60 * 60  # 24h
SCHEDULE_WINDOW_MINUTES = 5


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
        self._usage = UsageCounterRepository(session)
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
                await self._usage.increment(
                    project_id=draft.project_id,
                    day=_today_utc(),
                    posts_published=1,
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

    async def publish_due(self, project_id: int, now: datetime) -> PublicationLog | None:
        schedule_repo = ScheduleRepository(self._session)
        schedule = await schedule_repo.get_by_project_id(project_id)
        if not schedule or not schedule.enabled:
            return None

        tz = _safe_timezone(schedule.tz)
        now_local = _ensure_tz(now, tz)
        scheduled_at = _resolve_due_slot(now_local, schedule.slots_json)
        if not scheduled_at:
            return None

        channel = await self._channels.get_by_project_id(project_id)
        if not channel or channel.status != "connected":
            return None

        draft = await self._drafts.get_next_ready(project_id)
        if not draft:
            return None

        scheduled_at_utc = scheduled_at.astimezone(timezone.utc)
        existing_log = await self._logs.get_by_draft_and_scheduled(draft.id, scheduled_at_utc)
        if existing_log:
            return existing_log

        day_start_local = datetime.combine(now_local.date(), time.min, tzinfo=tz)
        day_end_local = day_start_local + timedelta(days=1)
        day_start_utc = day_start_local.astimezone(timezone.utc)
        day_end_utc = day_end_local.astimezone(timezone.utc)
        published_today = await self._logs.count_by_project_scheduled_between(
            project_id, day_start_utc, day_end_utc
        )
        if published_today >= schedule.per_day_limit:
            return None

        await self._quota.ensure_can_publish(project_id)

        message_id = await self._telegram_client.send_post(channel.channel_id, draft.text)
        draft.status = "published"
        self._session.add(draft)
        log = await self._logs.create_log(
            draft_id=draft.id,
            status="published",
            tg_message_id=message_id,
            published_at=datetime.now(timezone.utc),
            scheduled_at=scheduled_at_utc,
        )
        await self._usage.increment(
            project_id=project_id,
            day=_today_utc(),
            posts_published=1,
        )
        return log


def _safe_timezone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def _ensure_tz(value: datetime, tz: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(tz)


def _resolve_due_slot(now_local: datetime, slots_json: str) -> datetime | None:
    try:
        slots = json.loads(slots_json)
    except json.JSONDecodeError:
        slots = []

    candidates: list[datetime] = []
    for slot in slots:
        if not isinstance(slot, str):
            continue
        try:
            slot_time = time.fromisoformat(slot)
        except ValueError:
            continue
        slot_dt = datetime.combine(now_local.date(), slot_time, tzinfo=now_local.tzinfo)
        if now_local >= slot_dt:
            delta = now_local - slot_dt
            if delta <= timedelta(minutes=SCHEDULE_WINDOW_MINUTES):
                candidates.append(slot_dt)
    if not candidates:
        return None
    return max(candidates)


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()
