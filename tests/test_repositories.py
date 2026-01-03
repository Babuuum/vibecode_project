import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.domain import ProjectSettings
from autocontent.repos import ProjectRepository, ProjectSettingsRepository, UserRepository


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

    created = await settings_repo.create_settings(
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
