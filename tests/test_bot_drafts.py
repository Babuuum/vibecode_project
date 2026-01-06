from dataclasses import dataclass, field
from typing import Any, List

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from autocontent.bot.router import (
    draft_view_handler,
    drafts_list_handler,
    generate_now_handler,
    publish_draft_handler,
)
from autocontent.integrations.task_queue import TaskQueue
from autocontent.repos import (
    ChannelBindingRepository,
    PostDraftRepository,
    ProjectRepository,
    SourceItemRepository,
    SourceRepository,
    UserRepository,
)
from autocontent.shared.cooldown import InMemoryCooldownStore
from autocontent.shared.idempotency import InMemoryIdempotencyStore
from autocontent.shared.text import compute_content_hash
from autocontent.services.quota import NoopQuotaService

@dataclass
class FakeFromUser:
    id: int


@dataclass
class FakeMessage:
    text: str
    from_user: FakeFromUser
    answers: List[str] = field(default_factory=list)
    message_id: int = 1

    async def answer(self, text: str, **kwargs: Any) -> None:  # noqa: ARG002
        self.answers.append(text)


@dataclass
class FakeCallback:
    data: str
    message: FakeMessage
    answers: List[str] = field(default_factory=list)

    async def answer(self, text: str, **kwargs: Any) -> None:  # noqa: ARG002
        self.answers.append(text)


class FakeQueue(TaskQueue):
    def __init__(self) -> None:
        self.items: list[int] = []
        self.publish_items: list[int] = []

    def enqueue_generate_draft(self, source_item_id: int) -> None:
        self.items.append(source_item_id)

    def enqueue_publish_draft(self, draft_id: int) -> None:
        self.publish_items.append(draft_id)


@pytest.mark.asyncio
async def test_generate_now_enqueue_and_cooldown(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)

    user = await user_repo.create_user(tg_id=10)
    project = await project_repo.create_project(owner_user_id=user.id, title="P", tz="UTC")
    source = await source_repo.create_source(project_id=project.id, url="http://example.com/feed")
    item = await item_repo.create_item(
        source_id=source.id,
        external_id="ext",
        link="http://example.com/1",
        title="t",
        published_at=None,
        raw_text="raw",
        facts_cache=None,
        content_hash=compute_content_hash("http://example.com/1", "t", "raw"),
    )
    assert item is not None

    storage = MemoryStorage()
    state = FSMContext(storage, StorageKey(bot_id=0, user_id=user.id, chat_id=user.id))
    await state.update_data(project_id=project.id)
    msg = FakeMessage(text="Сгенерировать сейчас", from_user=FakeFromUser(id=user.tg_id))

    queue = FakeQueue()
    cooldown = InMemoryCooldownStore()

    quota = NoopQuotaService()
    await generate_now_handler(
        message=msg,
        state=state,
        session=session,
        task_queue=queue,
        cooldown_store=cooldown,
        quota_service=quota,
    )
    assert queue.items == [item.id]
    assert any("Поставил в очередь" in ans for ans in msg.answers)

    await generate_now_handler(
        message=msg,
        state=state,
        session=session,
        task_queue=queue,
        cooldown_store=cooldown,
        quota_service=quota,
    )
    assert queue.items == [item.id]
    assert any("Генерация уже запущена" in ans for ans in msg.answers)


@pytest.mark.asyncio
async def test_generate_now_no_sources(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)

    user = await user_repo.create_user(tg_id=20)
    project = await project_repo.create_project(owner_user_id=user.id, title="P2", tz="UTC")

    storage = MemoryStorage()
    state = FSMContext(storage, StorageKey(bot_id=0, user_id=user.id, chat_id=user.id))
    await state.update_data(project_id=project.id)
    msg = FakeMessage(text="Сгенерировать сейчас", from_user=FakeFromUser(id=user.tg_id))

    queue = FakeQueue()
    cooldown = InMemoryCooldownStore()
    await generate_now_handler(
        message=msg,
        state=state,
        session=session,
        task_queue=queue,
        cooldown_store=cooldown,
        quota_service=NoopQuotaService(),
    )

    assert queue.items == []
    assert any("Источники не добавлены" in ans for ans in msg.answers)


@pytest.mark.asyncio
async def test_drafts_list_and_view(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)
    drafts_repo = PostDraftRepository(session)

    user = await user_repo.create_user(tg_id=30)
    project = await project_repo.create_project(owner_user_id=user.id, title="P3", tz="UTC")
    source = await source_repo.create_source(project_id=project.id, url="http://example.com")
    item = await item_repo.create_item(
        source_id=source.id,
        external_id="ex2",
        link="http://example.com/2",
        title="title",
        published_at=None,
        raw_text="body",
        facts_cache=None,
        content_hash=compute_content_hash("http://example.com/2", "title", "body"),
    )
    assert item is not None
    draft = await drafts_repo.create_draft(
        project_id=project.id,
        source_item_id=item.id,
        template_id=None,
        text="draft text http://example.com/2",
        draft_hash=drafts_repo.compute_draft_hash(
            project_id=project.id,
            source_item_id=item.id,
            template_id=None,
            raw_text=item.raw_text or "",
        ),
    )

    storage = MemoryStorage()
    state = FSMContext(storage, StorageKey(bot_id=0, user_id=user.id, chat_id=user.id))
    await state.update_data(project_id=project.id)

    list_msg = FakeMessage(text="Черновики", from_user=FakeFromUser(id=user.tg_id))
    await drafts_list_handler(message=list_msg, state=state, session=session)
    assert any(str(draft.id) in ans for ans in list_msg.answers)

    view_msg = FakeMessage(text=f"/draft {draft.id}", from_user=FakeFromUser(id=user.tg_id))
    await draft_view_handler(message=view_msg, state=state, session=session)
    assert any("Драфт" in ans for ans in view_msg.answers)


@pytest.mark.asyncio
async def test_publish_callback_enqueue(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    channel_repo = ChannelBindingRepository(session)
    source_repo = SourceRepository(session)
    item_repo = SourceItemRepository(session)
    drafts_repo = PostDraftRepository(session)

    user = await user_repo.create_user(tg_id=31)
    project = await project_repo.create_project(owner_user_id=user.id, title="P4", tz="UTC")
    await channel_repo.create_or_update(project_id=project.id, channel_id="@ch", channel_username="@ch")
    await channel_repo.update_status(project_id=project.id, status="connected", last_error=None)
    source = await source_repo.create_source(project_id=project.id, url="http://example.com")
    item = await item_repo.create_item(
        source_id=source.id,
        external_id="ex3",
        link="http://example.com/3",
        title="title",
        published_at=None,
        raw_text="body",
        facts_cache=None,
        content_hash=compute_content_hash("http://example.com/3", "title", "body"),
    )
    assert item is not None
    draft = await drafts_repo.create_draft(
        project_id=project.id,
        source_item_id=item.id,
        template_id=None,
        text="draft text http://example.com/3",
        draft_hash=drafts_repo.compute_draft_hash(
            project_id=project.id,
            source_item_id=item.id,
            template_id=None,
            raw_text=item.raw_text or "",
        ),
    )

    storage = MemoryStorage()
    state = FSMContext(storage, StorageKey(bot_id=0, user_id=user.id, chat_id=user.id))
    await state.update_data(project_id=project.id)

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
