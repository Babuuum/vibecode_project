from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.domain import UsageCounter


class UsageCounterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_project_day(self, project_id: int, day: date) -> UsageCounter | None:
        stmt = select(UsageCounter).where(
            UsageCounter.project_id == project_id,
            UsageCounter.day == day,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def increment(
        self,
        project_id: int,
        day: date,
        drafts_generated: int = 0,
        posts_published: int = 0,
        llm_calls: int = 0,
        tokens_est: int = 0,
    ) -> UsageCounter:
        counter = await self.get_by_project_day(project_id, day)
        if not counter:
            counter = UsageCounter(
                project_id=project_id,
                day=day,
                drafts_generated=0,
                posts_published=0,
                llm_calls=0,
                tokens_est=0,
            )
            self._session.add(counter)
        counter.drafts_generated += drafts_generated
        counter.posts_published += posts_published
        counter.llm_calls += llm_calls
        counter.tokens_est += tokens_est
        await self._session.commit()
        await self._session.refresh(counter)
        return counter
