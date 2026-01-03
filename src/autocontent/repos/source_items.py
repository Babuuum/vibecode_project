from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.domain import SourceItem


class SourceItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_external_id(self, source_id: int, external_id: str) -> SourceItem | None:
        stmt = select(SourceItem).where(
            SourceItem.source_id == source_id, SourceItem.external_id == external_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_link(self, source_id: int, link: str) -> SourceItem | None:
        stmt = select(SourceItem).where(SourceItem.source_id == source_id, SourceItem.link == link)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_item(
        self,
        source_id: int,
        external_id: str,
        link: str,
        title: str,
        published_at: datetime | None,
        raw_text: str | None,
        content_hash: str,
        status: str = "new",
    ) -> SourceItem | None:
        existing = await self.get_by_external_id(source_id, external_id)
        if existing:
            return None
        existing = await self.get_by_link(source_id, link)
        if existing:
            return None

        item = SourceItem(
            source_id=source_id,
            external_id=external_id,
            link=link,
            title=title,
            published_at=published_at,
            raw_text=raw_text,
            content_hash=content_hash,
            status=status,
        )
        self._session.add(item)
        try:
            await self._session.commit()
            await self._session.refresh(item)
        except IntegrityError:
            await self._session.rollback()
            return None
        return item
