from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.autocontent.integrations.telegram_client import (
    ChannelForbiddenError,
    ChannelNotFoundError,
    TelegramClientError,
    TelegramClient,
)
from src.autocontent.repos import ChannelBindingRepository


class ChannelBindingNotFoundError(Exception):
    pass


class ChannelBindingService:
    def __init__(self, session: AsyncSession, telegram_client: TelegramClient) -> None:
        self._repo = ChannelBindingRepository(session)
        self._telegram_client = telegram_client

    async def save_binding(self, project_id: int, channel_id: str, channel_username: str | None) -> None:
        await self._repo.create_or_update(
            project_id=project_id, channel_id=channel_id, channel_username=channel_username
        )

    async def check_binding(self, project_id: int) -> None:
        binding = await self._repo.get_by_project_id(project_id)
        if not binding:
            raise ChannelBindingNotFoundError("Binding not found")

        try:
            await self._telegram_client.send_test_message(
                channel_id=binding.channel_id, text="Test message from AutoContent."
            )
            await self._repo.update_status(project_id, status="connected", last_error=None)
        except ChannelForbiddenError as exc:
            await self._repo.update_status(project_id, status="error", last_error=str(exc))
            raise
        except ChannelNotFoundError as exc:
            await self._repo.update_status(project_id, status="error", last_error=str(exc))
            raise
        except TelegramClientError as exc:
            await self._repo.update_status(project_id, status="error", last_error=str(exc))
            raise
