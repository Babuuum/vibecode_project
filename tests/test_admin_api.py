from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from autocontent.api import routes as api_routes
from autocontent.api.main import create_app
from autocontent.config import Settings
from autocontent.integrations.telegram_client import TelegramClient
from autocontent.repos import (
    ChannelBindingRepository,
    PostDraftRepository,
    ProjectRepository,
    ProjectSettingsRepository,
    SourceItemRepository,
    SourceRepository,
    UserRepository,
)
from autocontent.shared.db import Base
from autocontent.shared.text import compute_content_hash


class FakeTelegramClient(TelegramClient):
    async def send_test_message(self, channel_id: str, text: str) -> None:  # pragma: no cover
        return None

    async def send_post(self, channel_id: str, text: str) -> str:
        return "1"


async def _build_app() -> tuple:
    settings = Settings(
        postgres_dsn="sqlite+aiosqlite:///file::memory:?cache=shared&uri=true",
        admin_api_key="secret",
        bot_token="test",
    )
    app = create_app(settings)
    async with app.state.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return app, settings


@pytest.mark.asyncio
async def test_admin_list_projects() -> None:
    app, _settings = await _build_app()
    async with app.state.session_factory() as session:
        user_repo = UserRepository(session)
        project_repo = ProjectRepository(session)
        user = await user_repo.create_user(tg_id=100)
        await project_repo.create_project(owner_user_id=user.id, title="P1", tz="UTC")

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/admin/projects", headers={"X-API-Key": "secret"})

    assert resp.status_code == 200
    data = resp.json()
    assert data and data[0]["title"] == "P1"


@pytest.mark.asyncio
async def test_admin_list_drafts_by_status() -> None:
    app, _settings = await _build_app()
    async with app.state.session_factory() as session:
        user_repo = UserRepository(session)
        project_repo = ProjectRepository(session)
        source_repo = SourceRepository(session)
        item_repo = SourceItemRepository(session)
        draft_repo = PostDraftRepository(session)

        user = await user_repo.create_user(tg_id=200)
        project = await project_repo.create_project(owner_user_id=user.id, title="P2", tz="UTC")
        source = await source_repo.create_source(project_id=project.id, url="http://example.com/feed")
        item = await item_repo.create_item(
            source_id=source.id,
            external_id="1",
            link="http://example.com/1",
            title="Title",
            published_at=datetime.now(timezone.utc),
            raw_text="Body",
            content_hash=compute_content_hash("http://example.com/1", "Title", "Body"),
        )
        await draft_repo.create_draft(
            project_id=project.id,
            source_item_id=item.id,
            template_id=None,
            text="ready",
            draft_hash=draft_repo.compute_draft_hash(project.id, item.id, None, item.raw_text or ""),
            status="ready",
        )
        await draft_repo.create_draft(
            project_id=project.id,
            source_item_id=item.id,
            template_id=None,
            text="new",
            draft_hash=draft_repo.compute_draft_hash(project.id, item.id, "t2", item.raw_text or ""),
            status="new",
        )

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get(
            f"/admin/projects/{project.id}/drafts?status=ready",
            headers={"X-API-Key": "secret"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "ready"


@pytest.mark.asyncio
async def test_admin_publish_draft() -> None:
    app, _settings = await _build_app()

    async def _override_client():
        yield FakeTelegramClient()

    app.dependency_overrides[api_routes.get_telegram_client] = _override_client

    async with app.state.session_factory() as session:
        user_repo = UserRepository(session)
        project_repo = ProjectRepository(session)
        settings_repo = ProjectSettingsRepository(session)
        source_repo = SourceRepository(session)
        item_repo = SourceItemRepository(session)
        draft_repo = PostDraftRepository(session)
        channel_repo = ChannelBindingRepository(session)

        user = await user_repo.create_user(tg_id=300)
        project = await project_repo.create_project(owner_user_id=user.id, title="P3", tz="UTC")
        await settings_repo.create_settings(project_id=project.id, language="en", niche="tech", tone="formal")
        await channel_repo.create_or_update(
            project_id=project.id, channel_id="@channel", channel_username="@channel"
        )
        await channel_repo.update_status(project.id, status="connected")
        source = await source_repo.create_source(project_id=project.id, url="http://example.com/feed")
        item = await item_repo.create_item(
            source_id=source.id,
            external_id="1",
            link="http://example.com/1",
            title="Title",
            published_at=None,
            raw_text="Body",
            content_hash=compute_content_hash("http://example.com/1", "Title", "Body"),
        )
        draft = await draft_repo.create_draft(
            project_id=project.id,
            source_item_id=item.id,
            template_id=None,
            text="Draft body",
            draft_hash=draft_repo.compute_draft_hash(project.id, item.id, None, item.raw_text or ""),
            status="ready",
        )

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post(
            f"/admin/drafts/{draft.id}/publish",
            headers={"X-API-Key": "secret"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "published"
