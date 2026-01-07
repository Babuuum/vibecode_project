from datetime import UTC, datetime

import pytest

from autocontent.config import Settings
from autocontent.integrations.llm_client import MockLLMClient
from autocontent.repos import (
    ProjectRepository,
    ProjectSettingsRepository,
    SourceItemRepository,
    SourceRepository,
    UserRepository,
)
from autocontent.services.draft_service import DraftService


@pytest.mark.asyncio
async def test_template_changes_output(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    settings_repo = ProjectSettingsRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)

    user = await user_repo.create_user(tg_id=900)
    project_news = await project_repo.create_project(owner_user_id=user.id, title="News", tz="UTC")
    project_digest = await project_repo.create_project(
        owner_user_id=user.id, title="Digest", tz="UTC"
    )
    await settings_repo.create_settings(
        project_id=project_news.id,
        language="en",
        niche="tech",
        tone="formal",
        template_id="news",
        max_post_len=400,
    )
    await settings_repo.create_settings(
        project_id=project_digest.id,
        language="en",
        niche="tech",
        tone="formal",
        template_id="digest",
        max_post_len=400,
    )

    source_news = await source_repo.create_source(
        project_id=project_news.id, url="http://example.com/news"
    )
    source_digest = await source_repo.create_source(
        project_id=project_digest.id, url="http://example.com/digest"
    )

    raw_text = "Same content for both templates"
    item_news = await item_repo.create_item(
        source_id=source_news.id,
        external_id="n1",
        link="http://example.com/n1",
        title="Title",
        published_at=datetime.now(UTC),
        raw_text=raw_text,
        content_hash="hash-news",
    )
    item_digest = await item_repo.create_item(
        source_id=source_digest.id,
        external_id="d1",
        link="http://example.com/d1",
        title="Title",
        published_at=datetime.now(UTC),
        raw_text=raw_text,
        content_hash="hash-digest",
    )

    llm = MockLLMClient(default_max_tokens=512)
    settings = Settings(llm_mode="normal")
    service = DraftService(session, llm_client=llm, settings=settings)

    draft_news = await service.generate_draft(item_news.id)
    draft_digest = await service.generate_draft(item_digest.id)

    assert draft_news.text != draft_digest.text
