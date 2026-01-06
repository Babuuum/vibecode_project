from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from autocontent.config import Settings
from autocontent.domain import PostDraft
from autocontent.integrations.llm_client import MockLLMClient
from autocontent.repos import (
    PostDraftRepository,
    ProjectRepository,
    ProjectSettingsRepository,
    SourceItemRepository,
    SourceRepository,
    UserRepository,
)
from autocontent.services.draft_service import DraftGenerationError, DraftService


@pytest.mark.asyncio
async def test_antirepeat_window_check(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)
    draft_repo = PostDraftRepository(session)

    user = await user_repo.create_user(tg_id=900)
    project = await project_repo.create_project(owner_user_id=user.id, title="P", tz="UTC")
    source = await source_repo.create_source(project_id=project.id, url="http://example.com/feed")
    item = await item_repo.create_item(
        source_id=source.id,
        external_id="x",
        link="http://example.com/1",
        title="Title",
        published_at=None,
        raw_text="Body",
        content_hash="hash",
    )
    assert item is not None

    draft = await draft_repo.create_draft(
        project_id=project.id,
        source_item_id=item.id,
        template_id=None,
        text="draft",
        draft_hash=draft_repo.compute_draft_hash(project.id, item.id, None, item.raw_text or ""),
        status="new",
    )

    old_time = datetime.now(timezone.utc) - timedelta(days=10)
    await session.execute(
        update(PostDraft).where(PostDraft.id == draft.id).values(created_at=old_time)
    )
    await session.commit()

    since = datetime.now(timezone.utc) - timedelta(days=7)
    assert await draft_repo.has_recent_hash(draft.draft_hash, since) is False


@pytest.mark.asyncio
async def test_antirepeat_blocks_duplicate_draft(session) -> None:
    settings = Settings(duplicate_window_days=7)
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    settings_repo = ProjectSettingsRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)
    draft_repo = PostDraftRepository(session)

    user = await user_repo.create_user(tg_id=901)
    project = await project_repo.create_project(owner_user_id=user.id, title="P2", tz="UTC")
    await settings_repo.create_settings(project_id=project.id, language="en", niche="tech", tone="formal")
    source = await source_repo.create_source(project_id=project.id, url="http://example.com/feed2")
    item1 = await item_repo.create_item(
        source_id=source.id,
        external_id="i1",
        link="http://example.com/1",
        title="Title",
        published_at=None,
        raw_text="Body",
        content_hash="same-hash",
    )
    item2 = await item_repo.create_item(
        source_id=source.id,
        external_id="i2",
        link="http://example.com/2",
        title="Title2",
        published_at=None,
        raw_text="Body",
        content_hash="same-hash",
    )
    assert item1 is not None
    assert item2 is not None

    service = DraftService(
        session,
        llm_client=MockLLMClient(default_max_tokens=50),
        settings=settings,
    )
    await service.generate_draft(item1.id)

    with pytest.raises(DraftGenerationError):
        await service.generate_draft(item2.id)

    assert await draft_repo.count() == 1
