from dataclasses import dataclass
from typing import Any, List

import pytest

from autocontent.bot.router import channel_check_handler
from autocontent.integrations.telegram_client import (
    ChannelForbiddenError,
    ChannelNotFoundError,
    TelegramClient,
)
from autocontent.repos import ChannelBindingRepository, ProjectRepository, UserRepository
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage


@dataclass
class FakeFromUser:
    id: int


@dataclass
class FakeMessage:
    text: str
    from_user: FakeFromUser
    answers: List[str]

    async def answer(self, text: str, **kwargs: Any) -> None:
        self.answers.append(text)


class FakeTelegramClient(TelegramClient):
    def __init__(self, behavior: str) -> None:
        self.behavior = behavior

    async def send_test_message(self, channel_id: str, text: str) -> None:
        if self.behavior == "forbidden":
            raise ChannelForbiddenError("forbidden")
        if self.behavior == "not_found":
            raise ChannelNotFoundError("not found")
        return None


@pytest.mark.asyncio
async def test_channel_check_success(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    channel_repo = ChannelBindingRepository(session)

    user = await user_repo.create_user(tg_id=7)
    project = await project_repo.create_project(owner_user_id=user.id, title="Proj", tz="UTC")
    await channel_repo.create_or_update(project_id=project.id, channel_id="@test", channel_username="@test")

    storage = MemoryStorage()
    key = StorageKey(bot_id=0, user_id=user.id, chat_id=user.id)
    state = FSMContext(storage, key)
    await state.update_data(project_id=project.id)

    message = FakeMessage(text="Проверить", from_user=FakeFromUser(id=user.tg_id), answers=[])
    client = FakeTelegramClient(behavior="ok")

    await channel_check_handler(message=message, state=state, session=session, telegram_client=client)
    assert any("Канал подключен" in ans for ans in message.answers)
    binding_after = await channel_repo.get_by_project_id(project.id)
    assert binding_after is not None
    assert binding_after.status == "connected"
    assert binding_after.last_error is None


@pytest.mark.asyncio
async def test_channel_check_forbidden(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    channel_repo = ChannelBindingRepository(session)

    user = await user_repo.create_user(tg_id=8)
    project = await project_repo.create_project(owner_user_id=user.id, title="Proj", tz="UTC")
    await channel_repo.create_or_update(project_id=project.id, channel_id="@test2", channel_username="@test2")

    storage = MemoryStorage()
    key = StorageKey(bot_id=0, user_id=user.id, chat_id=user.id)
    state = FSMContext(storage, key)
    await state.update_data(project_id=project.id)

    message = FakeMessage(text="Проверить", from_user=FakeFromUser(id=user.tg_id), answers=[])
    client = FakeTelegramClient(behavior="forbidden")

    await channel_check_handler(message=message, state=state, session=session, telegram_client=client)
    assert any("не может писать" in ans for ans in message.answers)
    binding_after = await channel_repo.get_by_project_id(project.id)
    assert binding_after is not None
    assert binding_after.status == "error"
    assert "forbidden" in (binding_after.last_error or "")


@pytest.mark.asyncio
async def test_channel_check_not_found(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    channel_repo = ChannelBindingRepository(session)

    user = await user_repo.create_user(tg_id=9)
    project = await project_repo.create_project(owner_user_id=user.id, title="Proj", tz="UTC")
    await channel_repo.create_or_update(project_id=project.id, channel_id="@test3", channel_username="@test3")

    storage = MemoryStorage()
    key = StorageKey(bot_id=0, user_id=user.id, chat_id=user.id)
    state = FSMContext(storage, key)
    await state.update_data(project_id=project.id)

    message = FakeMessage(text="Проверить", from_user=FakeFromUser(id=user.tg_id), answers=[])
    client = FakeTelegramClient(behavior="not_found")

    await channel_check_handler(message=message, state=state, session=session, telegram_client=client)
    assert any("не найден" in ans for ans in message.answers)
    binding_after = await channel_repo.get_by_project_id(project.id)
    assert binding_after is not None
    assert binding_after.status == "error"
    assert "not found" in (binding_after.last_error or "")
