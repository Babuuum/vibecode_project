from __future__ import annotations

from typing import Any, Iterable

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from autocontent.bot.source_states import SourceStates
from autocontent.integrations.telegram_client import (
    ChannelForbiddenError,
    ChannelNotFoundError,
    TelegramClient,
    TelegramClientError,
)
from autocontent.integrations.task_queue import CeleryTaskQueue, TaskQueue
from autocontent.services import ChannelBindingService, DraftService, ProjectService, SourceService
from autocontent.services.channel_binding import ChannelBindingNotFoundError
from autocontent.services.source_service import DuplicateSourceError
from autocontent.shared.cooldown import CooldownStore, InMemoryCooldownStore, RedisCooldownStore
from autocontent.config import Settings

try:
    from redis import asyncio as aioredis
except Exception:  # pragma: no cover
    aioredis = None

router = Router()


class OnboardingStates(StatesGroup):
    language = State()
    niche = State()
    tone = State()


class ChannelStates(StatesGroup):
    waiting_channel = State()


LANGUAGE_OPTIONS = ["en", "ru"]
NICHE_OPTIONS = ["tech", "marketing", "lifestyle"]
TONE_OPTIONS = ["friendly", "formal", "casual"]
CHANNEL_MENU = ["Настройки", "Подключить канал", "Проверить"]
DRAFT_MENU = ["Сгенерировать сейчас", "Черновики"]
SOURCE_MENU = ["Добавить RSS", "Список источников", "Fetch now"] + DRAFT_MENU + CHANNEL_MENU
COOLDOWN_TTL_SECONDS = 45

_default_task_queue: TaskQueue = CeleryTaskQueue()
if aioredis:
    try:
        _redis_client = aioredis.from_url(Settings().redis_url)
        _cooldown_store: CooldownStore = RedisCooldownStore(_redis_client)
    except Exception:
        _cooldown_store = InMemoryCooldownStore()
else:  # pragma: no cover
    _cooldown_store = InMemoryCooldownStore()


def _build_keyboard(options: Iterable[str]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=opt) for opt in options]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def _handle_db_error(message: Message) -> None:
    await message.answer("Сервис временно недоступен. Попробуйте позже.")


@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext, session: AsyncSession) -> Any:
    try:
        project_service = ProjectService(session)
        _, project = await project_service.ensure_user_and_project(message.from_user.id)  # type: ignore[arg-type]

        await state.update_data(project_id=project.id)
        await state.set_state(OnboardingStates.language)
        await message.answer(
            "Привет! Давай настроим твой проект. Выбери язык:",
            reply_markup=_build_keyboard(LANGUAGE_OPTIONS),
        )
    except SQLAlchemyError:
        await _handle_db_error(message)


@router.message(OnboardingStates.language)
async def language_handler(message: Message, state: FSMContext) -> Any:
    if message.text not in LANGUAGE_OPTIONS:
        await message.answer("Выбери язык из списка.", reply_markup=_build_keyboard(LANGUAGE_OPTIONS))
        return

    await state.update_data(language=message.text)
    await state.set_state(OnboardingStates.niche)
    await message.answer("Укажи нишу:", reply_markup=_build_keyboard(NICHE_OPTIONS))


@router.message(OnboardingStates.niche)
async def niche_handler(message: Message, state: FSMContext) -> Any:
    if message.text not in NICHE_OPTIONS:
        await message.answer("Выбери нишу из списка.", reply_markup=_build_keyboard(NICHE_OPTIONS))
        return

    await state.update_data(niche=message.text)
    await state.set_state(OnboardingStates.tone)
    await message.answer("Выбери тональность:", reply_markup=_build_keyboard(TONE_OPTIONS))


@router.message(OnboardingStates.tone)
async def tone_handler(message: Message, state: FSMContext, session: AsyncSession) -> Any:
    if message.text not in TONE_OPTIONS:
        await message.answer("Выбери тональность из списка.", reply_markup=_build_keyboard(TONE_OPTIONS))
        return

    data = await state.get_data()
    project_id = data.get("project_id")
    language = data.get("language")
    niche = data.get("niche")
    tone = message.text

    if not project_id or not language or not niche:
        await message.answer("Не хватает данных для сохранения настроек. Попробуй /start.")
        await state.clear()
        return

    try:
        project_service = ProjectService(session)
        settings = await project_service.save_settings(
            project_id=project_id,
            language=language,
            niche=niche,
            tone=tone,
        )
        await state.clear()
        await message.answer(
            "Настройки сохранены:\n"
            f"Язык: {settings.language}\n"
            f"Ниша: {settings.niche}\n"
            f"Тон: {settings.tone}",
            reply_markup=_build_keyboard(SOURCE_MENU),
        )
    except SQLAlchemyError:
        await _handle_db_error(message)


async def _resolve_project_id(message: Message, state: FSMContext, session: AsyncSession) -> int | None:
    data = await state.get_data()
    project_id = data.get("project_id")
    if project_id:
        return project_id

    project_service = ProjectService(session)
    project = await project_service.get_first_project_by_user(message.from_user.id)  # type: ignore[arg-type]
    if not project:
        return None
    await state.update_data(project_id=project.id)
    return project.id


@router.message(F.text == "Настройки")
@router.message(Command("settings"))
async def settings_handler(message: Message, state: FSMContext, session: AsyncSession) -> Any:
    try:
        project_id = await _resolve_project_id(message, state, session)
        if not project_id:
            await message.answer("Пользователь или проект не найден. Начните заново: /start.")
            return

        project_service = ProjectService(session)
        settings = await project_service.get_settings(project_id)
        if not settings:
            await message.answer("Настройки пока не заданы. Пройдите онбординг заново: /start.")
            return

        await message.answer(
            "Текущие настройки:\n"
            f"Язык: {settings.language}\n"
            f"Ниша: {settings.niche}\n"
            f"Тон: {settings.tone}\n"
            f"Шаблон: {settings.template_id or '-'}\n"
            f"Макс. длина: {settings.max_post_len}\n"
            f"Safe mode: {settings.safe_mode}\n"
            f"Автопостинг: {settings.autopost_enabled}",
            parse_mode=ParseMode.HTML,
            reply_markup=_build_keyboard(SOURCE_MENU),
        )
    except SQLAlchemyError:
        await _handle_db_error(message)


@router.message(F.text == "Подключить канал")
async def channel_connect_handler(message: Message, state: FSMContext) -> Any:
    await state.set_state(ChannelStates.waiting_channel)
    await message.answer(
        "Пришли @username или id канала, куда бот должен постить. "
        "Добавь бота админом с правом писать и удалять сообщения.",
        reply_markup=_build_keyboard(SOURCE_MENU),
    )


@router.message(ChannelStates.waiting_channel)
async def channel_save_handler(
    message: Message, state: FSMContext, session: AsyncSession, telegram_client: TelegramClient
) -> Any:
    channel_id = message.text.strip() if message.text else None
    if not channel_id:
        await message.answer("Не удалось распознать канал, пришли @username или id.")
        return

    project_id = await _resolve_project_id(message, state, session)
    if not project_id:
        await message.answer("Проект не найден, начните заново: /start.")
        await state.clear()
        return

    service = ChannelBindingService(session, telegram_client)
    await service.save_binding(project_id=project_id, channel_id=channel_id, channel_username=channel_id)
    await state.clear()
    await message.answer(
        "Канал сохранен. Нажми «Проверить», чтобы отправить тестовое сообщение.",
        reply_markup=_build_keyboard(SOURCE_MENU),
    )


@router.message(F.text == "Проверить")
async def channel_check_handler(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    telegram_client: TelegramClient,
) -> Any:
    project_id = await _resolve_project_id(message, state, session)
    if not project_id:
        await message.answer("Проект не найден, начните заново: /start.")
        return

    service = ChannelBindingService(session, telegram_client)
    try:
        await service.check_binding(project_id)
        await message.answer("Канал подключен и доступен ✅", reply_markup=_build_keyboard(CHANNEL_MENU))
    except ChannelBindingNotFoundError:
        await message.answer("Сначала подключите канал через кнопку «Подключить канал».")
    except ChannelForbiddenError:
        await message.answer("Бот не может писать в канал. Проверь права администратора.")
    except ChannelNotFoundError:
        await message.answer("Канал не найден или недоступен. Проверь имя/ID.")
    except TelegramClientError as exc:
        await message.answer(str(exc))
    except SQLAlchemyError:
        await _handle_db_error(message)


@router.message(F.text == "Добавить RSS")
async def add_rss_handler(message: Message, state: FSMContext) -> Any:
    await state.set_state(SourceStates.waiting_rss_url)
    await message.answer("Пришли RSS URL для добавления.", reply_markup=_build_keyboard(SOURCE_MENU))


@router.message(SourceStates.waiting_rss_url)
async def save_rss_handler(message: Message, state: FSMContext, session: AsyncSession) -> Any:
    url = (message.text or "").strip()
    if not url.startswith("http"):
        await message.answer("Нужен корректный URL, начинающийся с http.")
        return

    project_id = await _resolve_project_id(message, state, session)
    if not project_id:
        await message.answer("Проект не найден, начните /start.")
        await state.clear()
        return

    service = SourceService(session)
    try:
        await service.add_source(project_id=project_id, url=url)
        await state.clear()
        await message.answer(
            "Источник добавлен. Используй «Fetch now» для проверки.",
            reply_markup=_build_keyboard(SOURCE_MENU),
        )
    except DuplicateSourceError:
        await message.answer("Такой источник уже добавлен.", reply_markup=_build_keyboard(SOURCE_MENU))
    except SQLAlchemyError:
        await _handle_db_error(message)


@router.message(F.text == "Список источников")
async def list_sources_handler(message: Message, state: FSMContext, session: AsyncSession) -> Any:
    project_id = await _resolve_project_id(message, state, session)
    if not project_id:
        await message.answer("Проект не найден, начните /start.")
        return

    service = SourceService(session)
    sources = await service.list_sources(project_id)
    if not sources:
        await message.answer("Источники не добавлены.")
        return

    lines = [
        f"{src.id}. {src.url} [{src.status}] last_fetch={src.last_fetch_at or '-'}"
        for src in sources
    ]
    await message.answer("\n".join(lines), reply_markup=_build_keyboard(SOURCE_MENU))


@router.message(F.text == "Fetch now")
async def fetch_now_handler(message: Message, state: FSMContext, session: AsyncSession) -> Any:
    project_id = await _resolve_project_id(message, state, session)
    if not project_id:
        await message.answer("Проект не найден, начните /start.")
        return

    service = SourceService(session)
    sources = await service.list_sources(project_id)
    if not sources:
        await message.answer("Нет источников для обновления.")
        return

    total_saved = await service.fetch_all_for_project(project_id)
    await message.answer(
        f"Fetch завершен. Новых записей: {total_saved}", reply_markup=_build_keyboard(SOURCE_MENU)
    )


def _resolve_cooldown_store(cooldown_store: CooldownStore | None) -> CooldownStore:
    return cooldown_store or _cooldown_store


def _resolve_task_queue(task_queue: TaskQueue | None) -> TaskQueue:
    return task_queue or _default_task_queue


@router.message(F.text == "Сгенерировать сейчас")
async def generate_now_handler(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    task_queue: TaskQueue | None = None,
    cooldown_store: CooldownStore | None = None,
) -> Any:
    project_id = await _resolve_project_id(message, state, session)
    if not project_id:
        await message.answer("Проект не найден, начните /start.")
        return

    service = SourceService(session)
    sources = await service.list_sources(project_id)
    if not sources:
        await message.answer("Источники не добавлены. Используй «Добавить RSS».")
        return

    item = await service.get_latest_new_item(project_id)
    if not item:
        await message.answer("Нет новых материалов для генерации. Попробуй Fetch now.")
        return

    cooldown = _resolve_cooldown_store(cooldown_store)
    if not await cooldown.acquire(f"draft:{project_id}", COOLDOWN_TTL_SECONDS):
        await message.answer("Генерация уже запущена. Подожди чуть-чуть и попробуй снова.")
        return

    queue = _resolve_task_queue(task_queue)
    queue.enqueue_generate_draft(item.id)
    await message.answer(
        f"Поставил в очередь генерацию драфта для материала #{item.id}.",
        reply_markup=_build_keyboard(SOURCE_MENU),
    )


@router.message(F.text == "Черновики")
async def drafts_list_handler(message: Message, state: FSMContext, session: AsyncSession) -> Any:
    project_id = await _resolve_project_id(message, state, session)
    if not project_id:
        await message.answer("Проект не найден, начните /start.")
        return

    service = DraftService(session)
    drafts = await service.list_drafts(project_id, limit=10)
    if not drafts:
        await message.answer("Черновиков пока нет.")
        return

    lines = [f"{draft.id}: [{draft.status}] {draft.text[:80]}" for draft in drafts]
    lines.append("Для просмотра: /draft <id>")
    await message.answer("\n".join(lines), reply_markup=_build_keyboard(SOURCE_MENU))


@router.message(Command("draft"))
async def draft_view_handler(message: Message, state: FSMContext, session: AsyncSession) -> Any:
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer("Используй: /draft <id>")
        return
    draft_id = int(args[1].strip())

    project_id = await _resolve_project_id(message, state, session)
    if not project_id:
        await message.answer("Проект не найден, начните /start.")
        return

    service = DraftService(session)
    draft = await service.get_draft(draft_id)
    if not draft or draft.project_id != project_id:
        await message.answer("Драфт не найден.")
        return

    await message.answer(
        f"Драфт #{draft.id} [{draft.status}]:\n{draft.text}",
        reply_markup=_build_keyboard(SOURCE_MENU),
        parse_mode=ParseMode.HTML,
    )
