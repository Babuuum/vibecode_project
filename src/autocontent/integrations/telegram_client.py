from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError


class TelegramClientError(Exception):
    """Base Telegram client error."""


class ChannelNotFoundError(TelegramClientError):
    """Channel not found or access denied."""


class ChannelForbiddenError(TelegramClientError):
    """Forbidden to send to channel."""


class TelegramClient(ABC):
    @abstractmethod
    async def send_test_message(self, channel_id: str, text: str) -> None:
        raise NotImplementedError


class AiogramTelegramClient(TelegramClient):
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_test_message(self, channel_id: str, text: str) -> None:
        try:
            message = await self._bot.send_message(chat_id=channel_id, text=text)
            try:
                await self._bot.delete_message(chat_id=channel_id, message_id=message.message_id)
            except TelegramBadRequest:
                # Ignore if we cannot delete
                pass
        except TelegramForbiddenError as exc:
            raise ChannelForbiddenError("Нет прав на отправку в канал.") from exc
        except TelegramBadRequest as exc:
            raise ChannelNotFoundError("Канал не найден или бот не админ.") from exc
        except TelegramNetworkError as exc:
            raise TelegramClientError("Сеть недоступна, повторите позже.") from exc
