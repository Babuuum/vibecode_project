import pytest

from autocontent.integrations.telegram_client import TelegramClient
from autocontent.repos import (
    ChannelBindingRepository,
    PostDraftRepository,
    ProjectRepository,
    SourceItemRepository,
    SourceRepository,
    UserRepository,
)
from autocontent.services.publication_service import PublicationService
from autocontent.shared.idempotency import InMemoryIdempotencyStore
from autocontent.shared.text import compute_content_hash


class FakeTelegramClient(TelegramClient):
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_test_message(self, channel_id: str, text: str) -> None:  # pragma: no cover
        return None

    async def send_post(self, channel_id: str, text: str) -> str:
        self.sent.append(text)
        return str(len(self.sent))


@pytest.mark.asyncio
async def test_publish_draft_idempotent(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    channel_repo = ChannelBindingRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)
    draft_repo = PostDraftRepository(session)

    user = await user_repo.create_user(tg_id=99)
    project = await project_repo.create_project(owner_user_id=user.id, title="P", tz="UTC")
    await channel_repo.create_or_update(project_id=project.id, channel_id="@channel", channel_username="@channel")
    await channel_repo.update_status(project.id, status="connected")

    source = await source_repo.create_source(project_id=project.id, url="http://example.com/feed")
    item = await item_repo.create_item(
        source_id=source.id,
        external_id="x",
        link="http://example.com/post",
        title="Title",
        published_at=None,
        raw_text="Some body",
        facts_cache=None,
        content_hash=compute_content_hash("http://example.com/post", "Title", "Some body"),
    )
    assert item is not None
    draft = await draft_repo.create_draft(
        project_id=project.id,
        source_item_id=item.id,
        template_id=None,
        text="Draft body",
        draft_hash=draft_repo.compute_draft_hash(project.id, item.id, None, item.raw_text or ""),
    )

    client = FakeTelegramClient()
    idempotency = InMemoryIdempotencyStore()
    service = PublicationService(session, telegram_client=client, idempotency_store=idempotency)

    log1 = await service.publish_draft(draft.id)
    log2 = await service.publish_draft(draft.id)

    assert log1.tg_message_id == "1"
    assert log2.tg_message_id == "1"
    assert len(client.sent) == 1
