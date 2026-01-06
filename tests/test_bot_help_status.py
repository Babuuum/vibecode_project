from dataclasses import dataclass, field
from typing import Any, List

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from src.autocontent.bot.router import help_handler, status_handler
from src.autocontent.repos import ProjectRepository, UserRepository


@dataclass
class FakeFromUser:
    id: int


@dataclass
class FakeMessage:
    text: str
    from_user: FakeFromUser
    answers: List[str] = field(default_factory=list)

    async def answer(self, text: str, **kwargs: Any) -> None:  # noqa: ARG002
        self.answers.append(text)


@pytest.mark.asyncio
async def test_help_command_smoke() -> None:
    message = FakeMessage(text="/help", from_user=FakeFromUser(id=1))
    await help_handler(message=message)

    assert message.answers
    assert "Чеклист" in message.answers[0]


@pytest.mark.asyncio
async def test_status_command_smoke(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)

    user = await user_repo.create_user(tg_id=555)
    await project_repo.create_project(owner_user_id=user.id, title="P", tz="UTC")

    storage = MemoryStorage()
    state = FSMContext(storage, StorageKey(bot_id=0, user_id=user.tg_id, chat_id=user.tg_id))
    message = FakeMessage(text="/status", from_user=FakeFromUser(id=user.tg_id))

    await status_handler(message=message, state=state, session=session)

    assert message.answers
    assert "Статус проекта" in message.answers[0]
