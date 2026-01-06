from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.domain import Schedule


class ScheduleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_project_id(self, project_id: int) -> Schedule | None:
        stmt = select(Schedule).where(Schedule.project_id == project_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_enabled(self) -> list[Schedule]:
        stmt = select(Schedule).where(Schedule.enabled.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_schedule(
        self,
        project_id: int,
        tz: str,
        slots: list[str],
        per_day_limit: int = 1,
        enabled: bool = True,
    ) -> Schedule:
        schedule = Schedule(
            project_id=project_id,
            tz=tz,
            slots_json=json.dumps(slots, ensure_ascii=True),
            per_day_limit=per_day_limit,
            enabled=enabled,
        )
        self._session.add(schedule)
        await self._session.commit()
        await self._session.refresh(schedule)
        return schedule

    async def update_schedule(
        self,
        schedule: Schedule,
        tz: str,
        slots: list[str],
        per_day_limit: int,
        enabled: bool,
    ) -> Schedule:
        schedule.tz = tz
        schedule.slots_json = json.dumps(slots, ensure_ascii=True)
        schedule.per_day_limit = per_day_limit
        schedule.enabled = enabled
        await self._session.commit()
        await self._session.refresh(schedule)
        return schedule
