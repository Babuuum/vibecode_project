from datetime import datetime, timezone

import pytest

from autocontent.integrations.telegram_client import RetryAfterError, TelegramClient
from autocontent.repos import (
    ChannelBindingRepository,
    PostDraftRepository,
    ProjectRepository,
    SourceItemRepository,
    SourceRepository,
    UserRepository,
)
from autocontent.services.publication_service import PublicationService
from autocontent.services.rate_limit import NoopRateLimiter
from autocontent.shared.idempotency import InMemoryIdempotencyStore
from autocontent.shared.text import compute_content_hash


class FlakyTelegramClient(TelegramClient):
    def __init__(self) -> None:
        self.calls = 0

    async def send_test_message(self, channel_id: str, text: str) -> None:  # pragma: no cover
        return None

    async def send_post(self, channel_id: str, text: str) -> str:
        self.calls += 1
        if self.calls == 1:
            raise RetryAfterError(5)
        return "1"


@pytest.mark.asyncio
async def test_publish_retries_with_retry_after(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    channel_repo = ChannelBindingRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)
    draft_repo = PostDraftRepository(session)

    user = await user_repo.create_user(tg_id=501)
    project = await project_repo.create_project(owner_user_id=user.id, title="P", tz="UTC")
    await channel_repo.create_or_update(project_id=project.id, channel_id="@ch", channel_username="@ch")
    await channel_repo.update_status(project.id, status="connected")
    source = await source_repo.create_source(project_id=project.id, url="http://example.com/feed")
    item = await item_repo.create_item(
        source_id=source.id,
        external_id="x",
        link="http://example.com/1",
        title="Title",
        published_at=datetime.now(timezone.utc),
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

    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    service = PublicationService(
        session=session,
        telegram_client=FlakyTelegramClient(),
        idempotency_store=InMemoryIdempotencyStore(),
        rate_limiter=NoopRateLimiter(),
        sleep_fn=fake_sleep,
    )

    log = await service.publish_draft(draft.id, max_retries=2)

    assert log.status == "published"
    assert delays == [5]
