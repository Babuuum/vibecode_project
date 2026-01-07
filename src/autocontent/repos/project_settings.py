from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.domain import ProjectSettings


class ProjectSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_settings(
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
        settings = ProjectSettings(
            project_id=project_id,
            language=language,
            niche=niche,
            tone=tone,
            template_id=template_id,
            max_post_len=max_post_len,
            safe_mode=safe_mode,
            autopost_enabled=autopost_enabled,
        )
        self._session.add(settings)
        await self._session.commit()
        await self._session.refresh(settings)
        return settings

    async def get_by_project_id(self, project_id: int) -> ProjectSettings | None:
        stmt = select(ProjectSettings).where(ProjectSettings.project_id == project_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_settings(
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
        existing = await self.get_by_project_id(project_id)
        if existing:
            existing.language = language
            existing.niche = niche
            existing.tone = tone
            existing.template_id = template_id
            existing.max_post_len = max_post_len
            existing.safe_mode = safe_mode
            existing.autopost_enabled = autopost_enabled
            await self._session.commit()
            await self._session.refresh(existing)
            return existing

        return await self.create_settings(
            project_id=project_id,
            language=language,
            niche=niche,
            tone=tone,
            template_id=template_id,
            max_post_len=max_post_len,
            safe_mode=safe_mode,
            autopost_enabled=autopost_enabled,
        )

    async def update_template_id(
        self, project_id: int, template_id: str | None
    ) -> ProjectSettings | None:
        settings = await self.get_by_project_id(project_id)
        if not settings:
            return None
        settings.template_id = template_id
        await self._session.commit()
        await self._session.refresh(settings)
        return settings
