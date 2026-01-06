from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.autocontent.domain import PublicationLog


class PublicationLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_draft_id(self, draft_id: int) -> PublicationLog | None:
        stmt = select(PublicationLog).where(PublicationLog.draft_id == draft_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

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
