from __future__ import annotations

from autocontent.domain.health import HealthStatus


class HealthService:
    async def get_status(self) -> HealthStatus:
        return HealthStatus()
