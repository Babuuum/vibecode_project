from datetime import UTC, datetime

import pytest

from autocontent.config import Settings
from autocontent.integrations.llm_client import MockLLMClient
from autocontent.integrations.telegram_client import TelegramClient
from autocontent.repos import (
    ChannelBindingRepository,
    ProjectRepository,
    ProjectSettingsRepository,
    SourceItemRepository,
    SourceRepository,
    UsageCounterRepository,
    UserRepository,
)
from autocontent.services.draft_service import DraftService
from autocontent.services.publication_service import PublicationService
from autocontent.shared.idempotency import InMemoryIdempotencyStore
from autocontent.shared.text import compute_content_hash


class FakeTelegramClient(TelegramClient):
    async def send_test_message(self, channel_id: str, text: str) -> None:  # pragma: no cover
        return None

    async def send_post(self, channel_id: str, text: str) -> str:
        return "1"


@pytest.mark.asyncio
async def test_usage_increment_repository(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    usage_repo = UsageCounterRepository(session)

    user = await user_repo.create_user(tg_id=800)
    project = await project_repo.create_project(owner_user_id=user.id, title="P", tz="UTC")
    day = datetime.now(UTC).date()

    await usage_repo.increment(project.id, day, drafts_generated=1, llm_calls=2, tokens_est=10)
    await usage_repo.increment(project.id, day, posts_published=1, tokens_est=5)

    usage = await usage_repo.get_by_project_day(project.id, day)
    assert usage is not None
    assert usage.drafts_generated == 1
    assert usage.posts_published == 1
    assert usage.llm_calls == 2
    assert usage.tokens_est == 15


@pytest.mark.asyncio
async def test_usage_updated_on_generate_and_publish(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    settings_repo = ProjectSettingsRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)
    channel_repo = ChannelBindingRepository(session)
    usage_repo = UsageCounterRepository(session)

    user = await user_repo.create_user(tg_id=801)
    project = await project_repo.create_project(owner_user_id=user.id, title="P", tz="UTC")
    await settings_repo.create_settings(
        project_id=project.id, language="en", niche="tech", tone="formal"
    )
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
        raw_text="Some body",
        facts_cache=None,
        content_hash=compute_content_hash("http://example.com/1", "Title", "Some body"),
    )

    llm = MockLLMClient(default_max_tokens=128)
    service = DraftService(session, llm_client=llm, settings=Settings(llm_mode="normal"))
    draft = await service.generate_draft(item.id)

    day = datetime.now(UTC).date()
    usage = await usage_repo.get_by_project_day(project.id, day)
    assert usage is not None
    assert usage.drafts_generated == 1
    assert usage.llm_calls == 2
    assert usage.tokens_est > 0

    publication = PublicationService(
        session,
        telegram_client=FakeTelegramClient(),
        idempotency_store=InMemoryIdempotencyStore(),
    )
    await publication.publish_draft(draft.id)

    usage = await usage_repo.get_by_project_day(project.id, day)
    assert usage is not None
    assert usage.posts_published == 1
