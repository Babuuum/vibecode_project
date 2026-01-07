from datetime import datetime, timezone

import pytest

from autocontent.integrations.telegram_client import TelegramClient
from autocontent.repos import (
    ChannelBindingRepository,
    PostDraftRepository,
    ProjectRepository,
    ProjectSettingsRepository,
    ScheduleRepository,
    SourceItemRepository,
    SourceRepository,
    UserRepository,
)
from autocontent.services.publication_service import PublicationService
from autocontent.shared.text import compute_content_hash


class FakeTelegramClient(TelegramClient):
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_test_message(self, channel_id: str, text: str) -> None:  # noqa: ARG002
        return None

    async def send_post(self, channel_id: str, text: str) -> str:  # noqa: ARG002
        self.sent.append(text)
        return str(len(self.sent))


@pytest.mark.asyncio
async def test_safe_mode_blocks_autopost(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    settings_repo = ProjectSettingsRepository(session)
    channel_repo = ChannelBindingRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)
    draft_repo = PostDraftRepository(session)
    schedule_repo = ScheduleRepository(session)

    user = await user_repo.create_user(tg_id=701)
    project = await project_repo.create_project(owner_user_id=user.id, title="P", tz="UTC")
    await settings_repo.create_settings(
        project_id=project.id,
        language="en",
        niche="tech",
        tone="formal",
        safe_mode=True,
        autopost_enabled=False,
    )
    await channel_repo.create_or_update(project_id=project.id, channel_id="@ch", channel_username="@ch")
    await channel_repo.update_status(project_id=project.id, status="connected", last_error=None)
    source = await source_repo.create_source(project_id=project.id, url="http://example.com/feed")
    item = await item_repo.create_item(
        source_id=source.id,
        external_id="x1",
        link="http://example.com/1",
        title="Title",
        published_at=None,
        raw_text="Body",
        content_hash=compute_content_hash("http://example.com/1", "Title", "Body"),
    )
    assert item is not None
    draft = await draft_repo.create_draft(
        project_id=project.id,
        source_item_id=item.id,
        template_id=None,
        text="Draft body",
        draft_hash=draft_repo.compute_draft_hash(project.id, item.id, None, item.raw_text or ""),
        status="ready",
    )

    await schedule_repo.create_schedule(
        project_id=project.id,
        tz="UTC",
        slots=["10:00"],
        per_day_limit=1,
        enabled=True,
    )

    client = FakeTelegramClient()
    service = PublicationService(session, telegram_client=client)
    now = datetime(2025, 1, 1, 10, 2, tzinfo=timezone.utc)
    log = await service.publish_due(project.id, now=now)

    assert log is None
    updated = await draft_repo.get_by_id(draft.id)
    assert updated is not None
    assert updated.status == "needs_approval"
    assert client.sent == []
