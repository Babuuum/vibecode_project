from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from aiogram import Bot

from src.autocontent.config import Settings
from src.autocontent.infrastructure.celery_app import celery_app
from src.autocontent.integrations.telegram_client import AiogramTelegramClient, TransientTelegramError
from src.autocontent.services.draft_service import DraftService
from src.autocontent.services.publication_service import PublicationService
from src.autocontent.services.rss_fetcher import fetch_and_save_source
from src.autocontent.shared.db import create_engine_from_settings, create_session_factory
from src.autocontent.shared.idempotency import InMemoryIdempotencyStore, RedisIdempotencyStore
from src.autocontent.services.quota import QuotaService
from src.autocontent.repos import SourceRepository

try:
    from redis import asyncio as aioredis
except Exception:  # pragma: no cover
    aioredis = None


@celery_app.task(name="fetch_source")
def fetch_source_task(source_id: int) -> None:
    async def _run() -> None:
        settings = Settings()
        engine = create_engine_from_settings(settings)
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            await fetch_and_save_source(source_id, session)
        await engine.dispose()

    asyncio.run(_run())


@celery_app.task(name="fetch_all_sources")
def fetch_all_sources_task() -> None:
    async def _run() -> None:
        settings = Settings()
        engine = create_engine_from_settings(settings)
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            repo = SourceRepository(session)
            sources = await repo.list_all()
            for src in sources:
                if src.status == "broken" and src.last_fetch_at:
                    backoff_seconds = src.fetch_interval_min * 3 * 60
                    delta = (datetime.now(timezone.utc) - src.last_fetch_at).total_seconds()
                    if delta < backoff_seconds:
                        continue
                await fetch_and_save_source(src.id, session)
        await engine.dispose()

    asyncio.run(_run())


@celery_app.task(name="generate_draft")
def generate_draft_task(source_item_id: int) -> None:
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

    asyncio.run(_run())


@celery_app.task(
    name="publish_draft",
    autoretry_for=(TransientTelegramError,),
    retry_backoff=5,
    retry_kwargs={"max_retries": 3},
)
def publish_draft_task(draft_id: int) -> None:
    async def _run() -> None:
        settings = Settings()
        engine = create_engine_from_settings(settings)
        session_factory = create_session_factory(engine)
        idempotency_store = InMemoryIdempotencyStore()
        quota_service = None
        if aioredis:
            try:
                redis_client = aioredis.from_url(settings.redis_url)
                idempotency_store = RedisIdempotencyStore(redis_client)
                quota_service = QuotaService(redis_client, settings=settings)
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
                settings=settings,
            )
            await service.publish_draft(draft_id)
        await engine.dispose()

    asyncio.run(_run())
