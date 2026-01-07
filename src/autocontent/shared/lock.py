from __future__ import annotations

import time
from typing import Protocol

try:
    from redis.asyncio import Redis
except Exception:  # pragma: no cover
    Redis = None  # type: ignore[assignment]


class LockStore(Protocol):
    async def acquire(self, key: str, ttl: int) -> bool: ...


class InMemoryLockStore:
    def __init__(self) -> None:
        self._storage: dict[str, float] = {}

    async def acquire(self, key: str, ttl: int) -> bool:
        now = time.monotonic()
        expires_at = self._storage.get(key, 0)
        if expires_at > now:
            return False
        self._storage[key] = now + ttl
        return True


class RedisLockStore:
    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    async def acquire(self, key: str, ttl: int) -> bool:
        return bool(await self._redis.set(key, "1", ex=ttl, nx=True))
