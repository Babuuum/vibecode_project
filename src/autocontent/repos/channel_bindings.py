from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.domain import ChannelBinding


class ChannelBindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_project_id(self, project_id: int) -> ChannelBinding | None:
        stmt = select(ChannelBinding).where(ChannelBinding.project_id == project_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_or_update(
        self, project_id: int, channel_id: str, channel_username: str | None
    ) -> ChannelBinding:
        existing = await self.get_by_project_id(project_id)
        if existing:
            existing.channel_id = channel_id
            existing.channel_username = channel_username
            existing.status = "pending"
            existing.last_check_at = None
            existing.last_error = None
            await self._session.commit()
            await self._session.refresh(existing)
            return existing

        binding = ChannelBinding(
            project_id=project_id,
            channel_id=channel_id,
            channel_username=channel_username,
            status="pending",
        )
        self._session.add(binding)
        await self._session.commit()
        await self._session.refresh(binding)
        return binding

    async def update_status(
        self, project_id: int, status: str, last_error: str | None = None
    ) -> ChannelBinding | None:
        binding = await self.get_by_project_id(project_id)
        if not binding:
            return None

        binding.status = status
        binding.last_check_at = datetime.now(UTC)
        binding.last_error = last_error
        await self._session.commit()
        await self._session.refresh(binding)
        return binding
