from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from aiogram import Bot
from celery import current_task
import structlog

from autocontent.config import Settings
from autocontent.infrastructure.celery_app import celery_app
from autocontent.integrations.telegram_client import AiogramTelegramClient, TransientTelegramError
from autocontent.services.draft_service import DraftService
from autocontent.services.publication_service import PublicationService
from autocontent.services.rss_fetcher import fetch_and_save_source
from autocontent.shared.db import create_engine_from_settings, create_session_factory
from autocontent.shared.idempotency import InMemoryIdempotencyStore, RedisIdempotencyStore
from autocontent.shared.lock import InMemoryLockStore, RedisLockStore
from autocontent.services.quota import QuotaService
from autocontent.services.rate_limit import RedisRateLimiter
from autocontent.repos import ScheduleRepository, SourceRepository
from autocontent.integrations.task_queue import CeleryTaskQueue
from autocontent.shared.logging import bind_log_context, clear_log_context, configure_logging


def _safe_job_id() -> str | None:
    try:
        return current_task.request.id
    except Exception:
        return None

try:
    from redis import asyncio as aioredis
except Exception:  # pragma: no cover
    aioredis = None


@celery_app.task(name="fetch_source")
def fetch_source_task(source_id: int) -> None:
    configure_logging()
    logger = structlog.get_logger(__name__)
    bind_log_context(job_id=_safe_job_id(), source_id=source_id)
    logger.info("task_start", task_name="fetch_source")
    async def _run() -> None:
        settings = Settings()
        engine = create_engine_from_settings(settings)
        session_factory = create_session_factory(engine)
        lock_store: InMemoryLockStore | RedisLockStore = InMemoryLockStore()
        if aioredis:
            try:
                redis_client = aioredis.from_url(settings.redis_url)
                lock_store = RedisLockStore(redis_client)
            except Exception:
                pass
        async with session_factory() as session:
            await fetch_and_save_source(
                source_id,
                session,
                task_queue=CeleryTaskQueue(),
                lock_store=lock_store,
                max_items_per_run=settings.max_generate_per_fetch,
            )
        await engine.dispose()

    try:
        asyncio.run(_run())
    finally:
        clear_log_context()


@celery_app.task(name="fetch_all_sources")
def fetch_all_sources_task() -> None:
    configure_logging()
    logger = structlog.get_logger(__name__)
    bind_log_context(job_id=_safe_job_id())
    logger.info("task_start", task_name="fetch_all_sources")
    async def _run() -> None:
        settings = Settings()
        engine = create_engine_from_settings(settings)
        session_factory = create_session_factory(engine)
        lock_store: InMemoryLockStore | RedisLockStore = InMemoryLockStore()
        if aioredis:
            try:
                redis_client = aioredis.from_url(settings.redis_url)
                lock_store = RedisLockStore(redis_client)
            except Exception:
                pass
        async with session_factory() as session:
            repo = SourceRepository(session)
            sources = await repo.list_all()
            for src in sources:
                if src.status == "broken" and src.last_fetch_at:
                    backoff_seconds = src.fetch_interval_min * 3 * 60
                    delta = (datetime.now(timezone.utc) - src.last_fetch_at).total_seconds()
                    if delta < backoff_seconds:
                        continue
                await fetch_and_save_source(
                    src.id,
                    session,
                    task_queue=CeleryTaskQueue(),
                    lock_store=lock_store,
                    max_items_per_run=settings.max_generate_per_fetch,
                )
        await engine.dispose()

    try:
        asyncio.run(_run())
    finally:
        clear_log_context()


@celery_app.task(name="generate_draft")
def generate_draft_task(source_item_id: int) -> None:
    configure_logging()
    logger = structlog.get_logger(__name__)
    bind_log_context(job_id=_safe_job_id(), source_item_id=source_item_id)
    logger.info("task_start", task_name="generate_draft")
    async def _run() -> None:
        settings = Settings()
        engine = create_engine_from_settings(settings)
        session_factory = create_session_factory(engine)
        quota_service = None
        if aioredis:
            try:
                redis_client = aioredis.from_url(settings.redis_url)
                quota_service = QuotaService(redis_client, settings=settings)
            except Exception:
                quota_service = None
        async with session_factory() as session:
            service = DraftService(session, quota_service=quota_service)
            await service.generate_draft(source_item_id)
        await engine.dispose()

    try:
        asyncio.run(_run())
    finally:
        clear_log_context()


@celery_app.task(
    name="publish_draft",
    autoretry_for=(TransientTelegramError,),
    retry_backoff=5,
    retry_kwargs={"max_retries": 3},
)
def publish_draft_task(draft_id: int) -> None:
    configure_logging()
    logger = structlog.get_logger(__name__)
    bind_log_context(job_id=_safe_job_id(), draft_id=draft_id)
    logger.info("task_start", task_name="publish_draft")
    async def _run() -> None:
        settings = Settings()
        engine = create_engine_from_settings(settings)
        session_factory = create_session_factory(engine)
        idempotency_store = InMemoryIdempotencyStore()
        quota_service = None
        rate_limiter = None
        if aioredis:
            try:
                redis_client = aioredis.from_url(settings.redis_url)
                idempotency_store = RedisIdempotencyStore(redis_client)
                quota_service = QuotaService(redis_client, settings=settings)
                rate_limiter = RedisRateLimiter(redis_client, settings=settings)
            except Exception:
                pass

        async with session_factory() as session:
            bot = Bot(settings.bot_token, parse_mode="HTML")
            telegram_client = AiogramTelegramClient(bot)
            service = PublicationService(
                session=session,
                telegram_client=telegram_client,
                idempotency_store=idempotency_store,
                quota_service=quota_service,
                rate_limiter=rate_limiter,
                settings=settings,
            )
            await service.publish_draft(draft_id)
        await engine.dispose()

    try:
        asyncio.run(_run())
    finally:
        clear_log_context()


@celery_app.task(name="publish_due_drafts")
def publish_due_drafts_task() -> None:
    configure_logging()
    logger = structlog.get_logger(__name__)
    bind_log_context(job_id=_safe_job_id())
    logger.info("task_start", task_name="publish_due_drafts")
    async def _run() -> None:
        settings = Settings()
        engine = create_engine_from_settings(settings)
        session_factory = create_session_factory(engine)
        quota_service = None
        rate_limiter = None
        if aioredis:
            try:
                redis_client = aioredis.from_url(settings.redis_url)
                quota_service = QuotaService(redis_client, settings=settings)
                rate_limiter = RedisRateLimiter(redis_client, settings=settings)
            except Exception:
                quota_service = None

        async with session_factory() as session:
            bot = Bot(settings.bot_token, parse_mode="HTML")
            telegram_client = AiogramTelegramClient(bot)
            service = PublicationService(
                session=session,
                telegram_client=telegram_client,
                quota_service=quota_service,
                rate_limiter=rate_limiter,
                settings=settings,
            )
            schedule_repo = ScheduleRepository(session)
            schedules = await schedule_repo.list_enabled()
            now = datetime.now(timezone.utc)
            for schedule in schedules:
                await service.publish_due(schedule.project_id, now=now)
        await engine.dispose()

    try:
        asyncio.run(_run())
    finally:
        clear_log_context()
