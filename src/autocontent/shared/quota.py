from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

try:
    from redis.asyncio import Redis
except Exception:  # pragma: no cover
    Redis = None  # type: ignore[assignment]


class QuotaExceeded(Exception):
    pass


@dataclass(frozen=True)
class QuotaLimits:
    drafts_per_day: int = 20
    publishes_per_day: int = 20
    sources_limit: int = 20


class QuotaStore(Protocol):
    async def increment(self, key: str, ttl: int) -> int: ...


def _ttl_until_day_end(now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    end = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((end - now).total_seconds()))


class InMemoryQuotaStore:
    def __init__(self) -> None:
        self._storage: dict[str, tuple[int, float]] = {}

    async def increment(self, key: str, ttl: int) -> int:
        now = time.monotonic()
        value, expires = self._storage.get(key, (0, 0))
        if expires < now:
            value = 0
        value += 1
        self._storage[key] = (value, now + ttl)
        return value


class RedisQuotaStore:
    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    async def increment(self, key: str, ttl: int) -> int:
        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl)
        res = await pipe.execute()
        return int(res[0])


class QuotaService:
    def __init__(self, store: QuotaStore, limits: QuotaLimits | None = None) -> None:
        self.store = store
        self.limits = limits or QuotaLimits()

    async def ensure_draft_quota(self, project_id: int) -> None:
        if await self._hit(f"quota:draft:{project_id}", self.limits.drafts_per_day):
            return
        raise QuotaExceeded("Исчерпан лимит генераций за день.")

    async def ensure_publish_quota(self, project_id: int) -> None:
        if await self._hit(f"quota:publish:{project_id}", self.limits.publishes_per_day):
            return
        raise QuotaExceeded("Исчерпан лимит публикаций за день.")

    async def _hit(self, key: str, limit: int) -> bool:
        ttl = _ttl_until_day_end()
        value = await self.store.increment(key, ttl)
        return value <= limit
