from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.domain import Source


class SourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_source(
        self, project_id: int, url: str, fetch_interval_min: int = 60, type: str = "rss"
    ) -> Source:
        source = Source(
            project_id=project_id,
            url=url,
            fetch_interval_min=fetch_interval_min,
            type=type,
        )
        self._session.add(source)
        await self._session.commit()
        await self._session.refresh(source)
        return source

    async def get_by_id(self, source_id: int) -> Source | None:
        stmt = select(Source).where(Source.id == source_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_project(self, project_id: int) -> list[Source]:
        stmt = select(Source).where(Source.project_id == project_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(self) -> list[Source]:
        stmt = select(Source)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        source_id: int,
        status: str,
        last_error: str | None = None,
        consecutive_failures: int | None = None,
    ) -> Source | None:
        source = await self.get_by_id(source_id)
        if not source:
            return None
        source.status = status
        source.last_error = last_error
        source.last_fetch_at = datetime.now(timezone.utc)
        if consecutive_failures is not None:
            source.consecutive_failures = consecutive_failures
        await self._session.commit()
        await self._session.refresh(source)
        return source
