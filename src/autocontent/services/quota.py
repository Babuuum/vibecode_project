from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Protocol

try:
    from redis.asyncio import Redis
except Exception:  # pragma: no cover
    Redis = None  # type: ignore[assignment]

from autocontent.config import Settings


class QuotaExceededError(Exception):
    pass


class QuotaBackend(Protocol):
    async def ensure_can_generate(self, project_id: int) -> None: ...

    async def ensure_can_publish(self, project_id: int) -> None: ...

    async def ensure_can_add_source(self, current_sources: int) -> None: ...

    async def ensure_can_call_llm(self, project_id: int) -> None: ...


class NoopQuotaService:
    async def ensure_can_generate(self, project_id: int) -> None:  # noqa: ARG002
        return

    async def ensure_can_publish(self, project_id: int) -> None:  # noqa: ARG002
        return

    async def ensure_can_add_source(self, current_sources: int) -> None:  # noqa: ARG002
        return

    async def ensure_can_call_llm(self, project_id: int) -> None:  # noqa: ARG002
        return


class QuotaService:
    def __init__(self, redis_client: Redis, settings: Settings | None = None) -> None:
        self._redis = redis_client
        self._settings = settings or Settings()

    def _ttl_to_end_of_day(self) -> int:
        now = datetime.now(timezone.utc)
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return int((tomorrow - now).total_seconds())

    def _key(self, kind: str, project_id: int) -> str:
        return f"quota:{kind}:{project_id}"

    async def _increment_with_limit(self, key: str, limit: int) -> None:
        value = await self._redis.incr(key)
        if value == 1:
            await self._redis.expire(key, self._ttl_to_end_of_day())
        if value > limit:
            raise QuotaExceededError(f"Quota exceeded for {key}")

    async def ensure_can_generate(self, project_id: int) -> None:
        await self._increment_with_limit(
            self._key("drafts", project_id), self._settings.drafts_per_day
        )

    async def ensure_can_publish(self, project_id: int) -> None:
        await self._increment_with_limit(
            self._key("publishes", project_id), self._settings.publishes_per_day
        )

    async def ensure_can_add_source(self, current_sources: int) -> None:
        if current_sources >= self._settings.sources_limit:
            raise QuotaExceededError("Sources limit exceeded")

    async def ensure_can_call_llm(self, project_id: int) -> None:
        await self._increment_with_limit(
            self._key("llm_calls", project_id), self._settings.llm_calls_per_day
        )
