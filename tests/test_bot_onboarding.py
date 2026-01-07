from dataclasses import dataclass, field
from typing import Any

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from autocontent.bot.router import (
    OnboardingStates,
    language_handler,
    niche_handler,
    settings_handler,
    start_handler,
    tone_handler,
)
from autocontent.repos import ProjectRepository, ProjectSettingsRepository, UserRepository


@dataclass
class FakeFromUser:
    id: int


@dataclass
class FakeMessage:
    text: str
    from_user: FakeFromUser
    answers: list[str] = field(default_factory=list)

    async def answer(self, text: str, **kwargs: Any) -> None:
        self.answers.append(text)


@pytest.mark.asyncio
async def test_fsm_flow_transitions(session) -> None:
    storage = MemoryStorage()
    key = StorageKey(bot_id=0, user_id=1, chat_id=1)
    state = FSMContext(storage, key)

    message = FakeMessage(text="/start", from_user=FakeFromUser(id=1))
    await start_handler(message=message, state=state, session=session)
    assert await state.get_state() == OnboardingStates.language.state

    message.text = "en"
    await language_handler(message=message, state=state)
    assert await state.get_state() == OnboardingStates.niche.state

    message.text = "tech"
    await niche_handler(message=message, state=state)
    assert await state.get_state() == OnboardingStates.tone.state

    message.text = "friendly"
    await tone_handler(message=message, state=state, session=session)
    assert await state.get_state() is None
    assert any("Настройки сохранены" in ans for ans in message.answers)


@pytest.mark.asyncio
async def test_settings_handler_returns_saved_settings(session) -> None:
    # Prepare data
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    settings_repo = ProjectSettingsRepository(session)

    user = await user_repo.create_user(tg_id=42)
    project = await project_repo.create_project(owner_user_id=user.id, title="P1", tz="UTC")
    await settings_repo.upsert_settings(
        project_id=project.id,
        language="ru",
        niche="tech",
        tone="formal",
    )

    storage = MemoryStorage()
    key = StorageKey(bot_id=0, user_id=user.id, chat_id=user.id)
    state = FSMContext(storage, key)
    await state.update_data(project_id=project.id)

    message = FakeMessage(text="Настройки", from_user=FakeFromUser(id=user.tg_id))
    await settings_handler(message=message, state=state, session=session)

    assert any("Текущие настройки" in ans for ans in message.answers)
