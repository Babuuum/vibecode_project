from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.domain import PostDraft, PublicationLog


class PublicationLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_draft_id(self, draft_id: int) -> PublicationLog | None:
        stmt = select(PublicationLog).where(PublicationLog.draft_id == draft_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_draft_and_scheduled(
        self, draft_id: int, scheduled_at: datetime
    ) -> PublicationLog | None:
        stmt = select(PublicationLog).where(
            PublicationLog.draft_id == draft_id,
            PublicationLog.scheduled_at == scheduled_at,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_by_project_scheduled_between(
        self, project_id: int, start_at: datetime, end_at: datetime
    ) -> int:
        stmt = (
            select(func.count(PublicationLog.id))
            .join(PostDraft, PostDraft.id == PublicationLog.draft_id)
            .where(
                PostDraft.project_id == project_id,
                PublicationLog.scheduled_at >= start_at,
                PublicationLog.scheduled_at < end_at,
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def create_log(
        self,
        draft_id: int,
        status: str,
        tg_message_id: str | None = None,
        error_code: str | None = None,
        error_text: str | None = None,
        published_at=None,
        scheduled_at=None,
    ) -> PublicationLog:
        if scheduled_at is not None:
            existing = await self.get_by_draft_and_scheduled(draft_id, scheduled_at)
            if existing:
                return existing
        else:
            existing = await self.get_by_draft_id(draft_id)
            if existing:
                return existing

        log = PublicationLog(
            draft_id=draft_id,
            scheduled_at=scheduled_at,
            published_at=published_at,
            status=status,
            tg_message_id=tg_message_id,
            error_code=error_code,
            error_text=error_text,
        )
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(log)
        return log
