import pytest

from autocontent.config import Settings
from autocontent.services.rate_limit import RateLimitExceededError, RedisRateLimiter


class FakeRedis:
    def __init__(self) -> None:
        self.storage: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.storage[key] = self.storage.get(key, 0) + 1
        return self.storage[key]

    async def expire(self, key: str, ttl: int) -> None:
        self.ttls[key] = ttl

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -1)


@pytest.mark.asyncio
async def test_rate_limiter_blocks_after_limit() -> None:
    redis = FakeRedis()
    settings = Settings(publishes_per_hour=1)
    limiter = RedisRateLimiter(redis, settings=settings)

    await limiter.ensure_can_publish(1)
    with pytest.raises(RateLimitExceededError) as exc:
        await limiter.ensure_can_publish(1)

    assert exc.value.retry_after == 3600
