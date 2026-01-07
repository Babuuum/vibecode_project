from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.domain import Project


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_project(
        self, owner_user_id: int, title: str, tz: str, status: str = "active"
    ) -> Project:
        project = Project(owner_user_id=owner_user_id, title=title, tz=tz, status=status)
        self._session.add(project)
        await self._session.commit()
        await self._session.refresh(project)
        return project

    async def get_by_id(self, project_id: int) -> Project | None:
        stmt = select(Project).where(Project.id == project_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_first_by_owner(self, owner_user_id: int) -> Project | None:
        stmt = select(Project).where(Project.owner_user_id == owner_user_id).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Project]:
        stmt = select(Project).order_by(Project.id.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
