from __future__ import annotations

from collections.abc import AsyncIterator

from aiogram import Bot
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.api.schemas import HealthResponse
from autocontent.config import Settings
from autocontent.integrations.telegram_client import AiogramTelegramClient, TelegramClient
from autocontent.repos import PostDraftRepository, ProjectRepository, SourceRepository
from autocontent.services import HealthService
from autocontent.services.publication_service import PublicationError, PublicationService
from autocontent.services.rss_fetcher import fetch_and_save_source
from autocontent.shared.db import get_session

api_router = APIRouter()
health_service = HealthService()


async def get_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory = request.app.state.session_factory
    async for session in get_session(session_factory):
        yield session


async def require_admin(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> None:
    if not x_api_key or x_api_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")


async def get_telegram_client(
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> AsyncIterator[TelegramClient]:
    bot = Bot(token=settings.bot_token)
    client = AiogramTelegramClient(bot)
    try:
        yield client
    finally:
        await bot.session.close()


@api_router.get("/healthz", response_model=HealthResponse, tags=["system"])
async def health_check() -> HealthResponse:
    status = await health_service.get_status()
    return HealthResponse(status=status.status)


@api_router.get("/admin/projects", dependencies=[Depends(require_admin)], tags=["admin"])
async def list_projects(session: AsyncSession = Depends(get_db_session)) -> list[dict]:  # noqa: B008
    repo = ProjectRepository(session)
    projects = await repo.list_all()
    return [
        {"id": project.id, "title": project.title, "tz": project.tz, "status": project.status}
        for project in projects
    ]


@api_router.get(
    "/admin/projects/{project_id}/sources", dependencies=[Depends(require_admin)], tags=["admin"]
)
async def list_project_sources(
    project_id: int,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> list[dict]:
    sources = await SourceRepository(session).list_by_project(project_id)
    return [
        {
            "id": source.id,
            "type": source.type,
            "url": source.url,
            "status": source.status,
            "last_error": source.last_error,
        }
        for source in sources
    ]


@api_router.get(
    "/admin/projects/{project_id}/drafts", dependencies=[Depends(require_admin)], tags=["admin"]
)
async def list_project_drafts(
    project_id: int,
    status: str | None = None,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> list[dict]:
    drafts = await PostDraftRepository(session).list_by_project(project_id, status=status)
    return [
        {
            "id": draft.id,
            "status": draft.status,
            "template_id": draft.template_id,
            "text": draft.text,
        }
        for draft in drafts
    ]


@api_router.post(
    "/admin/projects/{project_id}/run_fetch", dependencies=[Depends(require_admin)], tags=["admin"]
)
async def run_fetch(
    project_id: int,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
) -> dict:
    source_repo = SourceRepository(session)
    sources = await source_repo.list_by_project(project_id)
    saved_total = 0
    for source in sources:
        _, saved = await fetch_and_save_source(source.id, session)
        saved_total += saved
    return {"sources": len(sources), "items_saved": saved_total}


@api_router.post(
    "/admin/drafts/{draft_id}/publish", dependencies=[Depends(require_admin)], tags=["admin"]
)
async def publish_draft(
    draft_id: int,
    session: AsyncSession = Depends(get_db_session),  # noqa: B008
    telegram_client: TelegramClient = Depends(get_telegram_client),  # noqa: B008
) -> dict:
    service = PublicationService(session, telegram_client=telegram_client)
    try:
        log = await service.publish_draft(draft_id)
    except PublicationError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return {"status": log.status, "log_id": log.id}
