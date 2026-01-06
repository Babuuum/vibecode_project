from dataclasses import dataclass, field
from typing import Any, List

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from autocontent.bot.router import template_menu_handler, template_select_handler
from autocontent.repos import ProjectRepository, ProjectSettingsRepository, UserRepository


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
async def test_template_select_updates_settings(session) -> None:
    user_repo = UserRepository(session)
    project_repo = ProjectRepository(session)
    settings_repo = ProjectSettingsRepository(session)

    user = await user_repo.create_user(tg_id=910)
    project = await project_repo.create_project(owner_user_id=user.id, title="P", tz="UTC")
    await settings_repo.create_settings(project_id=project.id, language="en", niche="tech", tone="formal")

    storage = MemoryStorage()
    state = FSMContext(storage, StorageKey(bot_id=0, user_id=user.id, chat_id=user.id))
    await state.update_data(project_id=project.id)

    message = FakeMessage(text="Шаблоны", from_user=FakeFromUser(id=user.tg_id))
    await template_menu_handler(message=message, state=state, session=session)
    assert any("Текущий шаблон" in ans for ans in message.answers)

    message.text = "Шаблон: digest"
    await template_select_handler(message=message, state=state, session=session)

    settings = await settings_repo.get_by_project_id(project.id)
    assert settings is not None
    assert settings.template_id == "digest"
