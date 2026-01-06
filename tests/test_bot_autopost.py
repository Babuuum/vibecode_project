from dataclasses import dataclass, field
from typing import Any, List

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from autocontent.bot.router import (
    ScheduleStates,
    autopost_disable_handler,
    autopost_enable_handler,
    autopost_slots_save_handler,
)
from autocontent.repos import ProjectRepository, ScheduleRepository, UserRepository


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
async def test_autopost_slots_save(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    schedule_repo = ScheduleRepository(session)

    user = await user_repo.create_user(tg_id=701)
    project = await project_repo.create_project(owner_user_id=user.id, title="P", tz="UTC")

    storage = MemoryStorage()
    state = FSMContext(storage, StorageKey(bot_id=0, user_id=user.id, chat_id=user.id))
    await state.update_data(project_id=project.id)
    await state.set_state(ScheduleStates.waiting_slots)

    message = FakeMessage(text="10:00,14:00,18:00", from_user=FakeFromUser(id=user.tg_id))
    await autopost_slots_save_handler(message=message, state=state, session=session)

    schedule = await schedule_repo.get_by_project_id(project.id)
    assert schedule is not None
    assert schedule.slots_json


@pytest.mark.asyncio
async def test_autopost_enable_disable(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    schedule_repo = ScheduleRepository(session)

    user = await user_repo.create_user(tg_id=702)
    project = await project_repo.create_project(owner_user_id=user.id, title="P2", tz="UTC")

    storage = MemoryStorage()
    state = FSMContext(storage, StorageKey(bot_id=0, user_id=user.id, chat_id=user.id))
    await state.update_data(project_id=project.id)

    message = FakeMessage(text="Автопостинг: Вкл", from_user=FakeFromUser(id=user.tg_id))
    await autopost_enable_handler(message=message, state=state, session=session)

    schedule = await schedule_repo.get_by_project_id(project.id)
    assert schedule is not None
    assert schedule.enabled is True

    message.text = "Автопостинг: Выкл"
    await autopost_disable_handler(message=message, state=state, session=session)

    schedule = await schedule_repo.get_by_project_id(project.id)
    assert schedule is not None
    assert schedule.enabled is False
