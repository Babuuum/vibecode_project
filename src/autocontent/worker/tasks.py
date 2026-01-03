from __future__ import annotations

import asyncio

from aiogram import Bot

from autocontent.config import Settings
from autocontent.infrastructure.celery_app import celery_app
from autocontent.integrations.telegram_client import AiogramTelegramClient
from autocontent.services.draft_service import DraftService
from autocontent.services.publication_service import PublicationService
from autocontent.services.rss_fetcher import fetch_and_save_source
from autocontent.shared.db import create_engine_from_settings, create_session_factory
from autocontent.shared.idempotency import InMemoryIdempotencyStore, RedisIdempotencyStore

try:
    from redis import asyncio as aioredis
except Exception:  # pragma: no cover
    aioredis = None


@celery_app.task(name="fetch_source")
def fetch_source_task(source_id: int) -> None:
    async def _run() -> None:
        engine = create_engine_from_settings()
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            await fetch_and_save_source(source_id, session)
        await engine.dispose()

    asyncio.run(_run())


@celery_app.task(name="generate_draft")
def generate_draft_task(source_item_id: int) -> None:
    async def _run() -> None:
        engine = create_engine_from_settings()
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            service = DraftService(session)
            await service.generate_draft(source_item_id)
        await engine.dispose()

    asyncio.run(_run())


@celery_app.task(name="publish_draft")
def publish_draft_task(draft_id: int) -> None:
    async def _run() -> None:
        settings = Settings()
        engine = create_engine_from_settings(settings)
        session_factory = create_session_factory(engine)
        idempotency_store = InMemoryIdempotencyStore()
        if aioredis:
            try:
                redis_client = aioredis.from_url(settings.redis_url)
                idempotency_store = RedisIdempotencyStore(redis_client)
            except Exception:
                pass

        async with session_factory() as session:
            bot = Bot(settings.bot_token, parse_mode="HTML")
            telegram_client = AiogramTelegramClient(bot)
            service = PublicationService(
                session=session,
                telegram_client=telegram_client,
                idempotency_store=idempotency_store,
            )
            await service.publish_draft(draft_id)
        await engine.dispose()

    asyncio.run(_run())
