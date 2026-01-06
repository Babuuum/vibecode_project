import pytest

from autocontent.config import Settings
from autocontent.services.quota import QuotaExceededError, QuotaService


class FakeRedis:
    def __init__(self) -> None:
        self.storage: dict[str, int] = {}
        self.expire_called: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.storage[key] = self.storage.get(key, 0) + 1
        return self.storage[key]

    async def expire(self, key: str, ttl: int) -> None:  # noqa: ARG002
        self.expire_called[key] = ttl


@pytest.mark.asyncio
async def test_quota_service_limits() -> None:
    redis = FakeRedis()
    settings = Settings(drafts_per_day=1, publishes_per_day=1)
    quota = QuotaService(redis, settings=settings)

    await quota.ensure_can_generate(project_id=1)
    with pytest.raises(QuotaExceededError):
        await quota.ensure_can_generate(project_id=1)

    await quota.ensure_can_publish(project_id=2)
    with pytest.raises(QuotaExceededError):
        await quota.ensure_can_publish(project_id=2)
