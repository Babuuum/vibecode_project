from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message

from src.autocontent.integrations.telegram_client import TelegramClient


class TelegramClientMiddleware(BaseMiddleware):
    def __init__(self, telegram_client: TelegramClient) -> None:
        super().__init__()
        self._telegram_client = telegram_client

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        data["telegram_client"] = self._telegram_client
        return await handler(event, data)
