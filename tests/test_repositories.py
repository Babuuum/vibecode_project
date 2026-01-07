import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.domain import ProjectSettings
from autocontent.repos import (
    ProjectRepository,
    ProjectSettingsRepository,
    SourceItemRepository,
    SourceRepository,
    UserRepository,
)


@pytest.mark.asyncio
async def test_create_and_get_user(session: AsyncSession) -> None:
    user_repo = UserRepository(session)
    created = await user_repo.create_user(tg_id=12345)

    fetched = await user_repo.get_by_tg_id(12345)

    assert created.id is not None
    assert fetched is not None
    assert fetched.tg_id == 12345


@pytest.mark.asyncio
async def test_create_and_get_project(session: AsyncSession) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)

    user = await user_repo.create_user(tg_id=54321)
    project = await project_repo.create_project(owner_user_id=user.id, title="Test", tz="UTC")

    fetched = await project_repo.get_by_id(project.id)

    assert fetched is not None
    assert fetched.owner_user_id == user.id
    assert fetched.title == "Test"
    assert fetched.tz == "UTC"


@pytest.mark.asyncio
async def test_create_and_get_project_settings(session: AsyncSession) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    settings_repo = ProjectSettingsRepository(session)

    user = await user_repo.create_user(tg_id=11111)
    project = await project_repo.create_project(owner_user_id=user.id, title="Project", tz="UTC")

    await settings_repo.create_settings(
        project_id=project.id,
        language="en",
        niche="tech",
        tone="friendly",
        template_id="tpl-1",
        max_post_len=500,
        safe_mode=True,
        autopost_enabled=False,
    )

    fetched = await settings_repo.get_by_project_id(project.id)

    assert fetched is not None
    assert isinstance(fetched, ProjectSettings)
    assert fetched.project_id == project.id
    assert fetched.language == "en"


@pytest.mark.asyncio
async def test_source_item_repository_deduplicates(session: AsyncSession) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)

    user = await user_repo.create_user(tg_id=777)
    project = await project_repo.create_project(owner_user_id=user.id, title="Proj", tz="UTC")
    source = await source_repo.create_source(project_id=project.id, url="http://example.com/feed")

    first = await item_repo.create_item(
        source_id=source.id,
        external_id="ext-1",
        link="http://example.com/1",
        title="First",
        published_at=None,
        raw_text="text",
        content_hash="hash1",
    )
    duplicate = await item_repo.create_item(
        source_id=source.id,
        external_id="ext-1",
        link="http://example.com/1",
        title="First",
        published_at=None,
        raw_text="text",
        content_hash="hash1",
    )

    assert first is not None
    assert duplicate is None
