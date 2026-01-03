from dataclasses import dataclass


@dataclass(slots=True)
class HealthStatus:
    status: str = "ok"
