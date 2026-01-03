from __future__ import annotations

from autocontent.infrastructure.celery_app import celery_app
from autocontent.services.rss_fetcher import fetch_and_save_source
from autocontent.shared.db import create_engine_from_settings, create_session_factory


@celery_app.task(name="fetch_source")
def fetch_source_task(source_id: int) -> None:
    import asyncio

    async def _run() -> None:
        engine = create_engine_from_settings()
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            await fetch_and_save_source(source_id, session)
        await engine.dispose()

    asyncio.run(_run())
