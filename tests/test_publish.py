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
from autocontent.services.draft_service import compute_draft_hash
from autocontent.services.publication_service import PublicationService
from autocontent.shared.idempotency import InMemoryIdempotencyStore
from autocontent.shared.text import compute_content_hash


class FakeTelegramClient(TelegramClient):
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_test_message(self, channel_id: str, text: str) -> None:  # noqa: ARG002
        return None

    async def send_post(self, channel_id: str, text: str) -> str:
        self.sent.append((channel_id, text))
        return str(len(self.sent))


@pytest.mark.asyncio
async def test_publish_draft_idempotent(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    channel_repo = ChannelBindingRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)
    drafts_repo = PostDraftRepository(session)

    user = await user_repo.create_user(tg_id=1)
    project = await project_repo.create_project(owner_user_id=user.id, title="P", tz="UTC")
    await channel_repo.create_or_update(
        project_id=project.id, channel_id="@ch", channel_username="@ch"
    )
    await channel_repo.update_status(project_id=project.id, status="connected", last_error=None)
    source = await source_repo.create_source(project_id=project.id, url="http://example.com")
    item = await item_repo.create_item(
        source_id=source.id,
        external_id="1",
        link="http://example.com/1",
        title="t",
        published_at=None,
        raw_text="raw",
        content_hash=compute_content_hash("http://example.com/1", "t", "raw"),
    )
    assert item is not None
    draft = await drafts_repo.create_draft(
        project_id=project.id,
        source_item_id=item.id,
        template_id=None,
        text="hello world",
        draft_hash=compute_draft_hash(project.id, item.id, None, item.raw_text or ""),
    )

    telegram_client = FakeTelegramClient()
    idem = InMemoryIdempotencyStore()
    service = PublicationService(session, telegram_client=telegram_client, idempotency_store=idem)

    await service.publish_draft(draft.id)
    await service.publish_draft(draft.id)

    assert len(telegram_client.sent) == 1
