from __future__ import annotations

from datetime import timedelta
from typing import Protocol

from autocontent.config import Settings


class RateLimitExceededError(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Rate limit exceeded")
        self.retry_after = retry_after


class RateLimiter(Protocol):
    async def ensure_can_publish(self, project_id: int) -> None: ...


class NoopRateLimiter:
    async def ensure_can_publish(self, project_id: int) -> None:  # noqa: ARG002
        return


class RedisRateLimiter:
    def __init__(self, redis_client, settings: Settings | None = None) -> None:
        self._redis = redis_client
        self._settings = settings or Settings()
        self._window_seconds = int(timedelta(hours=1).total_seconds())

    def _key(self, project_id: int) -> str:
        return f"rate:publish:{project_id}"

    async def ensure_can_publish(self, project_id: int) -> None:
        key = self._key(project_id)
        value = await self._redis.incr(key)
        if value == 1:
            await self._redis.expire(key, self._window_seconds)
        if value > self._settings.publishes_per_hour:
            ttl = await self._redis.ttl(key)
            retry_after = ttl if ttl and ttl > 0 else self._window_seconds
            raise RateLimitExceededError(retry_after=retry_after)
