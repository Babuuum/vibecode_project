from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from autocontent.bot.router import router
from autocontent.bot.session_middleware import SessionMiddleware
from autocontent.bot.telegram_client_middleware import TelegramClientMiddleware
from autocontent.config import Settings
from autocontent.integrations.telegram_client import AiogramTelegramClient
from autocontent.shared.db import create_engine_from_settings, create_session_factory

try:
    import sentry_sdk
except Exception:  # pragma: no cover
    sentry_sdk = None


async def start_bot(settings: Settings | None = None) -> None:
    settings = settings or Settings()
    if sentry_sdk and settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)
    bot = Bot(settings.bot_token, parse_mode="HTML")

    engine = create_engine_from_settings(settings)
    session_factory = create_session_factory(engine)
    telegram_client = AiogramTelegramClient(bot)

    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.message.middleware(SessionMiddleware(session_factory))
    dispatcher.message.middleware(TelegramClientMiddleware(telegram_client))
    dispatcher.include_router(router)

    await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())


def run() -> None:
    asyncio.run(start_bot())
