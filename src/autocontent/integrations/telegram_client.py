from __future__ import annotations

from abc import ABC, abstractmethod

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)


class TelegramClientError(Exception):
    """Base Telegram client error."""


class ChannelNotFoundError(TelegramClientError):
    """Channel not found or access denied."""


class ChannelForbiddenError(TelegramClientError):
    """Forbidden to send to channel."""


class TransientTelegramError(TelegramClientError):
    """Retryable Telegram transport error."""


class RetryAfterError(TelegramClientError):
    """Rate limited by Telegram."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("Retry after")
        self.retry_after = retry_after


class TelegramClient(ABC):
    @abstractmethod
    async def send_test_message(self, channel_id: str, text: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send_post(self, channel_id: str, text: str) -> str:
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
        except TelegramRetryAfter as exc:
            raise RetryAfterError(exc.retry_after) from exc
        except TelegramForbiddenError as exc:
            raise ChannelForbiddenError("Нет прав на отправку в канал.") from exc
        except TelegramBadRequest as exc:
            raise ChannelNotFoundError("Канал не найден или бот не админ.") from exc
        except TelegramNetworkError as exc:
            raise TransientTelegramError("Сеть недоступна, повторите позже.") from exc

    async def send_post(self, channel_id: str, text: str) -> str:
        try:
            message = await self._bot.send_message(chat_id=channel_id, text=text)
            return str(message.message_id)
        except TelegramRetryAfter as exc:
            raise RetryAfterError(exc.retry_after) from exc
        except TelegramForbiddenError as exc:
            raise ChannelForbiddenError("Бот не может отправить сообщение в канал.") from exc
        except TelegramBadRequest as exc:
            raise ChannelNotFoundError("Канал не найден или недоступен.") from exc
        except TelegramNetworkError as exc:
            raise TransientTelegramError("Сеть недоступна, повторите позже.") from exc
