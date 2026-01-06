from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.config import Settings
from autocontent.domain import Source
from autocontent.integrations.rss_client import HttpRSSClient, RSSClient
from autocontent.repos import SourceItemRepository, SourceRepository
from autocontent.services.rss_fetcher import fetch_and_save_source
from autocontent.services.quota import QuotaExceededError


class DuplicateSourceError(Exception):
    pass


class SourceService:
    def __init__(
        self,
        session: AsyncSession,
        rss_client: RSSClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._repo = SourceRepository(session)
        self._items = SourceItemRepository(session)
        self._rss_client = rss_client or HttpRSSClient()
        self._settings = settings or Settings()

    async def add_source(self, project_id: int, url: str) -> None:
        existing_sources = await self._repo.list_by_project(project_id)
        if len(existing_sources) >= self._settings.sources_limit:
            raise QuotaExceededError("Превышен лимит источников для проекта.")
        try:
            await self._repo.create_source(project_id=project_id, url=url)
        except IntegrityError as exc:
            await self._session.rollback()
            raise DuplicateSourceError("Source already exists for this project") from exc

    async def list_sources(self, project_id: int):
        return await self._repo.list_by_project(project_id)

    async def fetch_source(self, source_id: int) -> tuple[Source | None, int]:
        return await fetch_and_save_source(source_id, self._session, rss_client=self._rss_client)

    async def fetch_all_for_project(self, project_id: int) -> int:
        sources = await self._repo.list_by_project(project_id)
        total_saved = 0
        for src in sources:
            _, saved = await self.fetch_source(src.id)
            total_saved += saved
        return total_saved

    async def list_sources(self, project_id: int):
        return await self._repo.list_by_project(project_id)

    async def get_latest_new_item(self, project_id: int):
        return await self._items.get_latest_new_for_project(project_id)
