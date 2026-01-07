from dataclasses import dataclass, field
from typing import Any

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from autocontent.bot.router import drafts_approval_handler, publish_draft_handler
from autocontent.integrations.task_queue import TaskQueue
from autocontent.repos import (
    ChannelBindingRepository,
    PostDraftRepository,
    ProjectRepository,
    ProjectSettingsRepository,
    SourceItemRepository,
    SourceRepository,
    UserRepository,
)
from autocontent.services.quota import NoopQuotaService
from autocontent.shared.idempotency import InMemoryIdempotencyStore
from autocontent.shared.text import compute_content_hash


@dataclass
class FakeFromUser:
    id: int


@dataclass
class FakeMessage:
    text: str
    from_user: FakeFromUser
    answers: list[str] = field(default_factory=list)
    message_id: int = 1

    async def answer(self, text: str, **kwargs: Any) -> None:  # noqa: ARG002
        self.answers.append(text)


@dataclass
class FakeCallback:
    data: str
    message: FakeMessage
    answers: list[str] = field(default_factory=list)

    async def answer(self, text: str, **kwargs: Any) -> None:  # noqa: ARG002
        self.answers.append(text)


class FakeQueue(TaskQueue):
    def __init__(self) -> None:
        self.publish_items: list[int] = []

    def enqueue_generate_draft(self, source_item_id: int) -> None:  # noqa: ARG002
        return None

    def enqueue_publish_draft(self, draft_id: int) -> None:
        self.publish_items.append(draft_id)


@pytest.mark.asyncio
async def test_approval_flow(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    settings_repo = ProjectSettingsRepository(session)
    channel_repo = ChannelBindingRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)
    drafts_repo = PostDraftRepository(session)

    user = await user_repo.create_user(tg_id=801)
    project = await project_repo.create_project(owner_user_id=user.id, title="P", tz="UTC")
    await settings_repo.create_settings(
        project_id=project.id, language="en", niche="tech", tone="formal"
    )
    await channel_repo.create_or_update(
        project_id=project.id, channel_id="@ch", channel_username="@ch"
    )
    await channel_repo.update_status(project_id=project.id, status="connected", last_error=None)
    source = await source_repo.create_source(project_id=project.id, url="http://example.com")
    item = await item_repo.create_item(
        source_id=source.id,
        external_id="ex1",
        link="http://example.com/1",
        title="title",
        published_at=None,
        raw_text="body",
        facts_cache=None,
        content_hash=compute_content_hash("http://example.com/1", "title", "body"),
    )
    assert item is not None
    draft = await drafts_repo.create_draft(
        project_id=project.id,
        source_item_id=item.id,
        template_id=None,
        text="draft text http://example.com/1",
        draft_hash=drafts_repo.compute_draft_hash(
            project_id=project.id,
            source_item_id=item.id,
            template_id=None,
            raw_text=item.raw_text or "",
        ),
        status="needs_approval",
    )

    storage = MemoryStorage()
    state = FSMContext(storage, StorageKey(bot_id=0, user_id=user.id, chat_id=user.id))
    await state.update_data(project_id=project.id)

    message = FakeMessage(text="На одобрение", from_user=FakeFromUser(id=user.tg_id))
    await drafts_approval_handler(message=message, state=state, session=session)
    assert any("needs_approval" in ans for ans in message.answers)

    queue = FakeQueue()
    cb = FakeCallback(
        data=f"publish:{draft.id}",
        message=FakeMessage(text="", from_user=FakeFromUser(id=user.tg_id)),
    )
    await publish_draft_handler(
        callback=cb,
        state=state,
        session=session,
        task_queue=queue,
        publish_store=InMemoryIdempotencyStore(),
        quota_service=NoopQuotaService(),
    )  # type: ignore[arg-type]

    assert queue.publish_items == [draft.id]
