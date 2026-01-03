from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.domain import Project, ProjectSettings, User
from autocontent.repos import ProjectRepository, ProjectSettingsRepository, UserRepository


class ProjectService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._projects = ProjectRepository(session)
        self._settings = ProjectSettingsRepository(session)

    async def ensure_user_and_project(self, tg_id: int) -> tuple[User, Project]:
        user = await self._users.get_by_tg_id(tg_id)
        if not user:
            user = await self._users.create_user(tg_id)

        project = await self._projects.get_first_by_owner(user.id)
        if not project:
            project = await self._projects.create_project(
                owner_user_id=user.id, title="Default project", tz="UTC"
            )
        return user, project

    async def get_first_project_by_user(self, tg_id: int) -> Project | None:
        user = await self._users.get_by_tg_id(tg_id)
        if not user:
            return None
        return await self._projects.get_first_by_owner(user.id)

    async def save_settings(
        self,
        project_id: int,
        language: str,
        niche: str,
        tone: str,
        template_id: str | None = None,
        max_post_len: int = 1000,
        safe_mode: bool = True,
        autopost_enabled: bool = False,
    ) -> ProjectSettings:
        return await self._settings.upsert_settings(
            project_id=project_id,
            language=language,
            niche=niche,
            tone=tone,
            template_id=template_id,
            max_post_len=max_post_len,
            safe_mode=safe_mode,
            autopost_enabled=autopost_enabled,
        )

    async def get_settings(self, project_id: int) -> ProjectSettings | None:
        return await self._settings.get_by_project_id(project_id)
