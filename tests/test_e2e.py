import pytest
from datetime import datetime, timezone

from src.autocontent.config import Settings
from src.autocontent.integrations.llm_client import MockLLMClient
from src.autocontent.integrations.telegram_client import TelegramClient
from src.autocontent.repos import (
    ChannelBindingRepository,
    PostDraftRepository,
    ProjectRepository,
    SourceItemRepository,
    SourceRepository,
    UserRepository,
)
from src.autocontent.services.draft_service import DraftService
from src.autocontent.services.publication_service import PublicationService, PublicationError
from src.autocontent.services.quota import QuotaExceededError, QuotaService
from src.autocontent.services.rss_fetcher import fetch_and_save_source
from src.autocontent.services.source_service import SourceService
from src.autocontent.shared.idempotency import InMemoryIdempotencyStore
from src.autocontent.shared.text import compute_content_hash


RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
  <title>Test Feed</title>
  <item>
    <title>First</title>
    <link>http://example.com/1</link>
    <guid>1</guid>
    <pubDate>Mon, 06 Sep 2021 00:01:00 +0000</pubDate>
    <description>Hello world</description>
  </item>
</channel>
</rss>
"""


class MockTelegramClient(TelegramClient):
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_test_message(self, channel_id: str, text: str) -> None:  # noqa: ARG002
        return None

    async def send_post(self, channel_id: str, text: str) -> str:
        self.sent.append((channel_id, text))
        return str(len(self.sent))


class FakeRSSClient:
    def __init__(self, content: str) -> None:
        self.content = content

    async def fetch(self, url: str) -> str:  # noqa: ARG002
        return self.content


class FailingRSSClient:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    async def fetch(self, url: str) -> str:  # noqa: ARG002
        raise self.exc


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, key: str, ttl: int) -> bool:
        self.expires[key] = ttl
        return True


@pytest.mark.asyncio
async def test_e2e_happy_path(session) -> None:
    settings = Settings()
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    channel_repo = ChannelBindingRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)
    drafts_repo = PostDraftRepository(session)

    user = await user_repo.create_user(tg_id=100)
    project = await project_repo.create_project(owner_user_id=user.id, title="P", tz="UTC")
    await channel_repo.create_or_update(project_id=project.id, channel_id="@ch", channel_username="@ch")
    await channel_repo.update_status(project_id=project.id, status="connected", last_error=None)

    source_service = SourceService(session, settings=settings)
    await source_service.add_source(project_id=project.id, url="http://example.com/rss")
    source = await source_repo.list_by_project(project.id)
    assert source
    rss_client = FakeRSSClient(RSS_SAMPLE)
    await fetch_and_save_source(source[0].id, session, rss_client=rss_client)

    items = await item_repo.get_latest_new_for_project(project.id)
    assert items is not None

    draft_service = DraftService(session, llm_client=MockLLMClient(default_max_tokens=50), settings=settings)
    draft = await draft_service.generate_draft(items.id)
    assert "http://example.com/1" in draft.text

    telegram = MockTelegramClient()
    publish_service = PublicationService(
        session=session,
        telegram_client=telegram,
        idempotency_store=InMemoryIdempotencyStore(),
    )
    log = await publish_service.publish_draft(draft.id)

    assert log.status == "published"
    assert telegram.sent and telegram.sent[0][1] == draft.text
    draft_after = await drafts_repo.get_by_id(draft.id)
    assert draft_after is not None and draft_after.status == "published"


@pytest.mark.asyncio
async def test_e2e_quota_block(session) -> None:
    settings = Settings(drafts_per_day=1, publishes_per_day=1)
    redis = FakeRedis()
    quota = QuotaService(redis, settings=settings)
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)

    user = await user_repo.create_user(tg_id=200)
    project = await project_repo.create_project(owner_user_id=user.id, title="P2", tz="UTC")
    source = await source_repo.create_source(project_id=project.id, url="http://example.com/rss2")
    item = await item_repo.create_item(
        source_id=source.id,
        external_id="e1",
        link="http://example.com/1",
        title="t",
        published_at=datetime.now(timezone.utc),
        raw_text="raw",
        content_hash=compute_content_hash("http://example.com/1", "t", "raw"),
    )
    assert item is not None

    draft_service = DraftService(session, llm_client=MockLLMClient(default_max_tokens=20), settings=settings, quota_service=quota)
    await draft_service.generate_draft(item.id)
    with pytest.raises(QuotaExceededError):
        await draft_service.generate_draft(item.id)

    telegram = MockTelegramClient()
    publish_service = PublicationService(
        session=session,
        telegram_client=telegram,
        idempotency_store=InMemoryIdempotencyStore(),
        quota_service=quota,
        settings=settings,
    )
    with pytest.raises(QuotaExceededError):
        await publish_service.publish_draft(draft_id=1)


@pytest.mark.asyncio
async def test_e2e_broken_source_after_failures(session) -> None:
    settings = Settings(source_fail_threshold=2)
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    source_repo = SourceRepository(session)

    user = await user_repo.create_user(tg_id=300)
    project = await project_repo.create_project(owner_user_id=user.id, title="P3", tz="UTC")
    source = await source_repo.create_source(project_id=project.id, url="http://broken")

    failing_client = FailingRSSClient(RuntimeError("fail"))
    for _ in range(settings.source_fail_threshold):
        await fetch_and_save_source(source.id, session, rss_client=failing_client)

    updated = await source_repo.get_by_id(source.id)
    assert updated is not None
    assert updated.status == "broken"
    assert updated.consecutive_failures == settings.source_fail_threshold
    assert "fail" in (updated.last_error or "")
