from __future__ import annotations

import json
from typing import Any, Iterable

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
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
from autocontent.repos import (
    ChannelBindingRepository,
    ProjectRepository,
    ScheduleRepository,
    SourceItemRepository,
    SourceRepository,
)
from autocontent.services import ChannelBindingService, DraftService, ProjectService, SourceService
from autocontent.services.channel_binding import ChannelBindingNotFoundError
from autocontent.services.quota import (
    NoopQuotaService,
    QuotaBackend,
    QuotaExceededError,
    QuotaService,
)
from autocontent.services.source_service import DuplicateSourceError
from autocontent.shared.cooldown import CooldownStore, InMemoryCooldownStore, RedisCooldownStore
from autocontent.shared.idempotency import IdempotencyStore, InMemoryIdempotencyStore, RedisIdempotencyStore
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


class ScheduleStates(StatesGroup):
    waiting_slots = State()
    waiting_limit = State()


LANGUAGE_OPTIONS = ["en", "ru"]
NICHE_OPTIONS = ["tech", "marketing", "lifestyle"]
TONE_OPTIONS = ["friendly", "formal", "casual"]
CHANNEL_MENU = ["Настройки", "Подключить канал", "Проверить"]
DRAFT_MENU = ["Сгенерировать сейчас", "Черновики"]
AUTPOST_MENU = [
    "Автопостинг: Вкл",
    "Автопостинг: Выкл",
    "Автопостинг: Показать",
    "Автопостинг: Слоты",
    "Автопостинг: Лимит",
    "Назад",
]
SLOT_PRESETS = ["10:00,14:00,18:00", "09:00,12:00,15:00,18:00", "08:00,12:00,20:00"]
SOURCE_MENU = ["Добавить RSS", "Добавить URL", "Список источников", "Fetch now", "Автопостинг"] + DRAFT_MENU + CHANNEL_MENU
SOURCE_STATUS_MENU = ["Статус источников"] + SOURCE_MENU
COOLDOWN_TTL_SECONDS = 45
STATUS_DRAFTS_LIMIT = 5
MAX_SLOTS = 6
DEFAULT_SLOTS = ["10:00", "14:00", "18:00"]

_default_task_queue: TaskQueue = CeleryTaskQueue()
if aioredis:
    try:
        _redis_client = aioredis.from_url(Settings().redis_url)
        _cooldown_store: CooldownStore = RedisCooldownStore(_redis_client)
        _publish_store: IdempotencyStore = RedisIdempotencyStore(_redis_client)
        _quota_service: QuotaService = QuotaService(_redis_client)
    except Exception:
        _cooldown_store = InMemoryCooldownStore()
        _publish_store = InMemoryIdempotencyStore()
        _quota_service = NoopQuotaService()
else:  # pragma: no cover
    _cooldown_store = InMemoryCooldownStore()
    _publish_store = InMemoryIdempotencyStore()
    _quota_service = NoopQuotaService()


def _build_keyboard(options: Iterable[str]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=opt) for opt in options]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def _handle_db_error(message: Message) -> None:
    await message.answer("Сервис временно недоступен. Попробуйте позже.")


def _format_onboarding_checklist() -> str:
    return (
        "Чеклист онбординга:\n"
        "1) /start — создать проект\n"
        "2) «Добавить RSS» — добавить источники\n"
        "3) «Подключить канал» — указать канал\n"
        "4) «Проверить» — проверить доступ к каналу\n"
        "5) «Fetch now» — подтянуть материалы\n"
        "6) «Сгенерировать сейчас» — получить драфт\n"
        "7) «Черновики» — открыть и опубликовать"
    )


async def _build_next_steps(
    project_id: int,
    session: AsyncSession,
    sources: list,
    channel_binding,
    drafts: list,
) -> list[str]:
    steps: list[str] = []
    if not channel_binding or channel_binding.status != "connected":
        steps.append("Подключи канал: «Подключить канал» → «Проверить».")
    if not sources:
        steps.append("Добавь RSS-источник: «Добавить RSS».")
    item_repo = SourceItemRepository(session)
    items_total = await item_repo.count_by_project(project_id)
    items_new = await item_repo.count_new_by_project(project_id)
    if sources and items_total == 0:
        steps.append("Сделай первичный fetch: «Fetch now».")
    if items_new == 0 and items_total > 0:
        steps.append("Нет новых материалов — запусти «Fetch now» позже.")
    if not drafts and items_total > 0:
        steps.append("Сгенерируй драфт: «Сгенерировать сейчас».")
    return steps


def _parse_slots(raw_text: str) -> list[str] | None:
    raw_slots = [item.strip() for item in raw_text.split(",") if item.strip()]
    if not raw_slots:
        return None
    slots: list[str] = []
    seen: set[str] = set()
    for item in raw_slots:
        parts = item.split(":")
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            return None
        hour = int(parts[0])
        minute = int(parts[1])
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return None
        slot = f"{hour:02d}:{minute:02d}"
        if slot not in seen:
            seen.add(slot)
            slots.append(slot)
    if len(slots) > MAX_SLOTS:
        return None
    slots.sort()
    return slots


def _load_slots(slots_json: str) -> list[str]:
    try:
        slots = json.loads(slots_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(slots, list):
        return []
    return [slot for slot in slots if isinstance(slot, str)]


def _format_slots(slots_json: str) -> str:
    normalized = _load_slots(slots_json)
    return ", ".join(normalized) if normalized else "-"


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
            reply_markup=_build_keyboard(SOURCE_STATUS_MENU),
        )
    except SQLAlchemyError:
        await _handle_db_error(message)


@router.message(Command("help"))
async def help_handler(message: Message) -> Any:
    await message.answer(_format_onboarding_checklist(), reply_markup=_build_keyboard(SOURCE_MENU))


@router.message(Command("status"))
async def status_handler(message: Message, state: FSMContext, session: AsyncSession) -> Any:
    project_id = await _resolve_project_id(message, state, session)
    if not project_id:
        await message.answer("Проект не найден. Начни с /start.")
        return

    project_repo = ProjectRepository(session)
    source_repo = SourceRepository(session)
    channel_repo = ChannelBindingRepository(session)
    drafts_service = DraftService(session)

    project = await project_repo.get_by_id(project_id)
    if not project:
        await message.answer("Проект не найден. Начни с /start.")
        return

    channel_binding = await channel_repo.get_by_project_id(project_id)
    sources = await source_repo.list_by_project(project_id)
    drafts = await drafts_service.list_drafts(project_id, limit=STATUS_DRAFTS_LIMIT)

    settings = Settings()
    lines = [
        "Статус проекта:",
        f"Проект: {project.title} [{project.status}] tz={project.tz}",
    ]

    if channel_binding:
        channel_label = channel_binding.channel_username or channel_binding.channel_id
        lines.append(f"Канал: {channel_label} [{channel_binding.status}]")
    else:
        lines.append("Канал: не подключен")

    if sources:
        status_counts: dict[str, int] = {}
        for src in sources:
            status_counts[src.status] = status_counts.get(src.status, 0) + 1
        status_part = ", ".join(f"{key}={val}" for key, val in sorted(status_counts.items()))
        lines.append(f"Источники: {len(sources)} ({status_part})")
    else:
        lines.append("Источники: 0")

    item_repo = SourceItemRepository(session)
    items_total = await item_repo.count_by_project(project_id)
    items_new = await item_repo.count_new_by_project(project_id)
    lines.append(f"Материалы: всего={items_total}, новых={items_new}")
    lines.append(
        "Квоты: "
        f"драфты/день={settings.drafts_per_day}, "
        f"публикации/день={settings.publishes_per_day}, "
        f"источники={settings.sources_limit}"
    )

    if drafts:
        lines.append("Последние драфты:")
        for draft in drafts:
            preview = draft.text.replace("\n", " ")[:80]
            lines.append(f"{draft.id} [{draft.status}] {preview}")
    else:
        lines.append("Последние драфты: нет")

    next_steps = await _build_next_steps(
        project_id=project_id,
        session=session,
        sources=sources,
        channel_binding=channel_binding,
        drafts=drafts,
    )
    if next_steps:
        lines.append("Следующие шаги:")
        lines.extend(f"- {step}" for step in next_steps)

    await message.answer("\n".join(lines), reply_markup=_build_keyboard(SOURCE_MENU))


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
            reply_markup=_build_keyboard(SOURCE_STATUS_MENU),
        )
    except SQLAlchemyError:
        await _handle_db_error(message)


@router.message(F.text == "Автопостинг")
async def autopost_menu_handler(message: Message) -> Any:
    await message.answer("Меню автопостинга:", reply_markup=_build_keyboard(AUTPOST_MENU))


@router.message(F.text == "Назад")
async def autopost_back_handler(message: Message) -> Any:
    await message.answer("Главное меню.", reply_markup=_build_keyboard(SOURCE_MENU))


@router.message(F.text == "Автопостинг: Показать")
async def autopost_show_handler(message: Message, state: FSMContext, session: AsyncSession) -> Any:
    project_id = await _resolve_project_id(message, state, session)
    if not project_id:
        await message.answer("Проект не найден. Начни с /start.")
        return

    schedule_repo = ScheduleRepository(session)
    schedule = await schedule_repo.get_by_project_id(project_id)
    if not schedule:
        await message.answer(
            "Расписание не задано. Используй «Автопостинг: Слоты».",
            reply_markup=_build_keyboard(AUTPOST_MENU),
        )
        return

    await message.answer(
        "Текущее расписание:\n"
        f"Включено: {schedule.enabled}\n"
        f"Часовой пояс: {schedule.tz}\n"
        f"Слоты: {_format_slots(schedule.slots_json)}\n"
        f"Лимит в день: {schedule.per_day_limit}",
        reply_markup=_build_keyboard(AUTPOST_MENU),
    )


@router.message(F.text == "Автопостинг: Вкл")
async def autopost_enable_handler(message: Message, state: FSMContext, session: AsyncSession) -> Any:
    project_id = await _resolve_project_id(message, state, session)
    if not project_id:
        await message.answer("Проект не найден. Начни с /start.")
        return

    project_repo = ProjectRepository(session)
    project = await project_repo.get_by_id(project_id)
    if not project:
        await message.answer("Проект не найден. Начни с /start.")
        return

    schedule_repo = ScheduleRepository(session)
    schedule = await schedule_repo.get_by_project_id(project_id)
    slots = DEFAULT_SLOTS
    per_day_limit = 1
    enabled = True
    if schedule:
        current_slots = _load_slots(schedule.slots_json)
        slots = current_slots or DEFAULT_SLOTS
        per_day_limit = schedule.per_day_limit
        await schedule_repo.update_schedule(
            schedule, tz=project.tz, slots=slots, per_day_limit=per_day_limit, enabled=enabled
        )
    else:
        await schedule_repo.create_schedule(
            project_id=project_id,
            tz=project.tz,
            slots=slots,
            per_day_limit=per_day_limit,
            enabled=enabled,
        )

    await message.answer(
        "Автопостинг включен.",
        reply_markup=_build_keyboard(AUTPOST_MENU),
    )


@router.message(F.text == "Автопостинг: Выкл")
async def autopost_disable_handler(message: Message, state: FSMContext, session: AsyncSession) -> Any:
    project_id = await _resolve_project_id(message, state, session)
    if not project_id:
        await message.answer("Проект не найден. Начни с /start.")
        return

    schedule_repo = ScheduleRepository(session)
    schedule = await schedule_repo.get_by_project_id(project_id)
    if not schedule:
        await message.answer("Расписание не задано.", reply_markup=_build_keyboard(AUTPOST_MENU))
        return

    await schedule_repo.update_schedule(
        schedule,
        tz=schedule.tz,
        slots=_load_slots(schedule.slots_json),
        per_day_limit=schedule.per_day_limit,
        enabled=False,
    )
    await message.answer("Автопостинг выключен.", reply_markup=_build_keyboard(AUTPOST_MENU))


@router.message(F.text == "Автопостинг: Слоты")
async def autopost_slots_handler(message: Message, state: FSMContext) -> Any:
    await state.set_state(ScheduleStates.waiting_slots)
    presets = SLOT_PRESETS + ["Назад"]
    await message.answer(
        "Введи слоты в формате HH:MM через запятую (до 6).",
        reply_markup=_build_keyboard(presets),
    )


@router.message(ScheduleStates.waiting_slots)
async def autopost_slots_save_handler(message: Message, state: FSMContext, session: AsyncSession) -> Any:
    text = (message.text or "").strip()
    if text == "Назад":
        await state.set_state(None)
        await message.answer("Меню автопостинга.", reply_markup=_build_keyboard(AUTPOST_MENU))
        return

    slots = _parse_slots(text)
    if not slots:
        await message.answer(
            "Неверный формат. Пример: 10:00,14:00,18:00 (до 6 слотов).",
            reply_markup=_build_keyboard(SLOT_PRESETS + ["Назад"]),
        )
        return

    project_id = await _resolve_project_id(message, state, session)
    if not project_id:
        await message.answer("Проект не найден. Начни с /start.")
        return

    project_repo = ProjectRepository(session)
    project = await project_repo.get_by_id(project_id)
    if not project:
        await message.answer("Проект не найден. Начни с /start.")
        return

    schedule_repo = ScheduleRepository(session)
    schedule = await schedule_repo.get_by_project_id(project_id)
    if schedule:
        await schedule_repo.update_schedule(
            schedule,
            tz=project.tz,
            slots=slots,
            per_day_limit=schedule.per_day_limit,
            enabled=schedule.enabled,
        )
    else:
        await schedule_repo.create_schedule(
            project_id=project_id,
            tz=project.tz,
            slots=slots,
            per_day_limit=1,
            enabled=False,
        )

    await state.set_state(None)
    await message.answer("Слоты сохранены.", reply_markup=_build_keyboard(AUTPOST_MENU))


@router.message(F.text == "Автопостинг: Лимит")
async def autopost_limit_handler(message: Message, state: FSMContext) -> Any:
    await state.set_state(ScheduleStates.waiting_limit)
    await message.answer("Укажи лимит публикаций в день (1-20).")


@router.message(ScheduleStates.waiting_limit)
async def autopost_limit_save_handler(message: Message, state: FSMContext, session: AsyncSession) -> Any:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Нужна цифра от 1 до 20.")
        return
    value = int(raw)
    if value < 1 or value > 20:
        await message.answer("Лимит должен быть от 1 до 20.")
        return

    project_id = await _resolve_project_id(message, state, session)
    if not project_id:
        await message.answer("Проект не найден. Начни с /start.")
        return

    project_repo = ProjectRepository(session)
    project = await project_repo.get_by_id(project_id)
    if not project:
        await message.answer("Проект не найден. Начни с /start.")
        return

    schedule_repo = ScheduleRepository(session)
    schedule = await schedule_repo.get_by_project_id(project_id)
    if schedule:
        await schedule_repo.update_schedule(
            schedule,
            tz=project.tz,
            slots=_load_slots(schedule.slots_json) or DEFAULT_SLOTS,
            per_day_limit=value,
            enabled=schedule.enabled,
        )
    else:
        await schedule_repo.create_schedule(
            project_id=project_id,
            tz=project.tz,
            slots=DEFAULT_SLOTS,
            per_day_limit=value,
            enabled=False,
        )

    await state.set_state(None)
    await message.answer("Лимит сохранен.", reply_markup=_build_keyboard(AUTPOST_MENU))


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
        await message.answer("Канал не подключен. Нажмите «Подключить канал».")
    except ChannelForbiddenError:
        await message.answer("Нет прав писать в канал. Добавьте бота админом с правом писать.")
    except ChannelNotFoundError:
        await message.answer("Канал не найден. Проверь @username/ID и что бот добавлен.")
    except TelegramClientError:
        await message.answer("Telegram недоступен. Попробуйте позже.")
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
            reply_markup=_build_keyboard(SOURCE_STATUS_MENU),
        )
    except DuplicateSourceError:
        await message.answer("Такой источник уже добавлен.", reply_markup=_build_keyboard(SOURCE_MENU))
    except QuotaExceededError:
        await message.answer("Достигнут лимит источников для проекта.", reply_markup=_build_keyboard(SOURCE_MENU))
    except SQLAlchemyError:
        await _handle_db_error(message)


@router.message(F.text == "Добавить URL")
async def add_url_handler(message: Message, state: FSMContext) -> Any:
    await state.set_state(SourceStates.waiting_page_url)
    await message.answer("Пришли URL страницы для добавления.", reply_markup=_build_keyboard(SOURCE_MENU))


@router.message(SourceStates.waiting_page_url)
async def save_url_handler(message: Message, state: FSMContext, session: AsyncSession) -> Any:
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
        await service.add_source(project_id=project_id, url=url, type="url")
        await state.clear()
        await message.answer(
            "Источник добавлен. Используй «Fetch now» для проверки.",
            reply_markup=_build_keyboard(SOURCE_STATUS_MENU),
        )
    except DuplicateSourceError:
        await message.answer("Такой источник уже добавлен.", reply_markup=_build_keyboard(SOURCE_MENU))
    except QuotaExceededError:
        await message.answer("Достигнут лимит источников для проекта.", reply_markup=_build_keyboard(SOURCE_MENU))
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
    await message.answer("\n".join(lines), reply_markup=_build_keyboard(SOURCE_STATUS_MENU))


@router.message(F.text == "Статус источников")
async def sources_status_handler(message: Message, state: FSMContext, session: AsyncSession) -> Any:
    project_id = await _resolve_project_id(message, state, session)
    if not project_id:
        await message.answer("Проект не найден, начните /start.")
        return

    service = SourceService(session)
    sources = await service.list_sources(project_id)
    if not sources:
        await message.answer("Источники не добавлены.", reply_markup=_build_keyboard(SOURCE_STATUS_MENU))
        return

    lines = []
    for src in sources:
        status = src.status
        lines.append(
            f"{src.id}. {src.url} [{status}] last_fetch={src.last_fetch_at or '-'} "
            f"errors={src.consecutive_failures} last_error={src.last_error or '-'}"
        )
    await message.answer("\n".join(lines), reply_markup=_build_keyboard(SOURCE_STATUS_MENU))


@router.message(F.text == "Fetch now")
async def fetch_now_handler(message: Message, state: FSMContext, session: AsyncSession) -> Any:
    project_id = await _resolve_project_id(message, state, session)
    if not project_id:
        await message.answer("Проект не найден, начните /start.")
        return

    service = SourceService(session)
    sources = await service.list_sources(project_id)
    if not sources:
        await message.answer("Нет источников для обновления. Добавьте RSS источник.")
        return

    try:
        total_saved = await service.fetch_all_for_project(project_id)
    except Exception:  # noqa: BLE001
        await message.answer("Не удалось обновить источники. Попробуйте позже.")
        return

    await message.answer(
        f"Fetch завершен. Новых записей: {total_saved}", reply_markup=_build_keyboard(SOURCE_MENU)
    )


def _resolve_cooldown_store(cooldown_store: CooldownStore | None) -> CooldownStore:
    return cooldown_store or _cooldown_store


def _resolve_task_queue(task_queue: TaskQueue | None) -> TaskQueue:
    return task_queue or _default_task_queue


def _resolve_publish_store(store: IdempotencyStore | None) -> IdempotencyStore:
    return store or _publish_store


def _resolve_quota_service(quota_service: QuotaBackend | None) -> QuotaBackend:
    return quota_service or _quota_service


@router.message(F.text == "Сгенерировать сейчас")
async def generate_now_handler(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    task_queue: TaskQueue | None = None,
    cooldown_store: CooldownStore | None = None,
    quota_service: QuotaBackend | None = None,
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
        await message.answer("Нет новых материалов. Запустите «Fetch now» и попробуйте позже.")
        return

    quota_service = _resolve_quota_service(quota_service)
    try:
        await quota_service.ensure_can_generate(project_id)
    except QuotaExceededError as exc:
        await message.answer(str(exc))
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
        reply_markup=_draft_actions_keyboard(draft.id),
        parse_mode=ParseMode.HTML,
    )


def _draft_actions_keyboard(draft_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"publish:{draft_id}"),
                InlineKeyboardButton(text="🗑️ Отклонить", callback_data=f"reject:{draft_id}"),
            ]
        ]
    )


@router.callback_query(F.data.startswith("publish:"))
async def publish_draft_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    task_queue: TaskQueue | None = None,
    publish_store: IdempotencyStore | None = None,
    quota_service: QuotaBackend | None = None,
) -> Any:
    draft_id = int(callback.data.split(":", 1)[1])
    project_id = await _resolve_project_id(callback.message, state, session)  # type: ignore[arg-type]
    if not project_id:
        await callback.answer("Проект не найден.")
        return

    draft_service = DraftService(session)
    draft = await draft_service.get_draft(draft_id)
    if not draft or draft.project_id != project_id:
        await callback.answer("Драфт не найден.")
        return

    quota_service = _resolve_quota_service(quota_service)
    try:
        await quota_service.ensure_can_publish(project_id)
    except QuotaExceededError as exc:
        await callback.answer(str(exc))
        return

    store = _resolve_publish_store(publish_store)
    if not await store.acquire(f"publish:{draft_id}", 24 * 60 * 60):
        await callback.answer("Публикация уже выполняется.")
        return

    queue = _resolve_task_queue(task_queue)
    queue.enqueue_publish_draft(draft_id)
    await callback.answer("Отправил в публикацию.")
    await callback.message.answer(
        f"Драфт #{draft.id} поставлен в очередь на публикацию.",
        reply_markup=_build_keyboard(SOURCE_MENU),
    )


@router.callback_query(F.data.startswith("reject:"))
async def reject_draft_handler(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> Any:
    draft_id = int(callback.data.split(":", 1)[1])
    project_id = await _resolve_project_id(callback.message, state, session)  # type: ignore[arg-type]
    if not project_id:
        await callback.answer("Проект не найден.")
        return

    draft_service = DraftService(session)
    draft = await draft_service.get_draft(draft_id)
    if not draft or draft.project_id != project_id:
        await callback.answer("Драфт не найден.")
        return

    await draft_service.reject_draft(draft_id)
    await callback.answer("Драфт отклонен.")
    await callback.message.answer("Драфт помечен как отклоненный.", reply_markup=_build_keyboard(SOURCE_MENU))
