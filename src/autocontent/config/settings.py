from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_env_file() -> str | None:
    env_file = os.getenv("ENV_FILE")
    if env_file:
        return env_file
    if os.getenv("PYTEST_CURRENT_TEST"):
        return None
    candidate = Path(".env")
    return str(candidate) if candidate.is_file() else None


class Settings(BaseSettings):
    """Application-wide settings with sensible defaults."""

    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(), env_file_encoding="utf-8", extra="allow"
    )

    app_name: str = "AutoContent TG"
    environment: str = "development"
    api_host: str = "0.0.0.0"  # noqa: S104
    api_port: int = 8000
    reload: bool = False
    log_level: str = "info"

    postgres_dsn: str = Field(
        default="postgresql+asyncpg://postgres:postgres@postgres:5432/autocontent",
        description="Async DB DSN (Postgres or SQLite).",
    )
    redis_url: str = Field(
        default="redis://redis:6379/0",
        description="Redis connection URL used for caching and Celery broker by default.",
    )
    celery_broker_url: str | None = Field(
        default=None, description="Optional Celery broker override (defaults to redis_url)."
    )
    celery_result_backend: str | None = Field(
        default=None, description="Optional Celery backend override (defaults to redis_url)."
    )
    bot_token: str = Field(
        default="dev-bot-token",
        description="Telegram bot token. Use a placeholder in development.",
    )
    admin_api_key: str = Field(
        default="dev-admin-key",
        description="Admin API key for /admin endpoints.",
    )
    sentry_dsn: str = Field(default="", description="Sentry DSN (optional).")
    sqlalchemy_echo: bool = False
    llm_provider: str = "mock"
    llm_api_key: str = ""
    llm_base_url: str = "http://llm:8000"
    llm_mode: str = Field(default="economy", description="economy|normal")
    llm_calls_per_day: int = 200
    drafts_per_day: int = 20
    publishes_per_day: int = 20
    publishes_per_hour: int = 5
    sources_limit: int = 10
    fetch_interval_min: int = 10
    source_fail_threshold: int = 3
    max_generate_per_fetch: int = 5
    generate_lock_ttl: int = 60
    duplicate_window_days: int = 7
    url_fetch_timeout_sec: int = 10
    url_max_chars: int = 200000
    url_text_max_chars: int = 8000
    source_text_max_chars: int = 8000

    def __init__(self, **values) -> None:
        super().__init__(**values)
        set_settings(self)

    @property
    def llm_max_tokens(self) -> int:
        return 128 if self.llm_mode == "economy" else 512

    @property
    def resolved_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def resolved_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


_CURRENT_SETTINGS: Settings | None = None


def get_settings() -> Settings:
    global _CURRENT_SETTINGS
    if _CURRENT_SETTINGS is None:
        _CURRENT_SETTINGS = Settings()
    return _CURRENT_SETTINGS


def set_settings(settings: Settings) -> None:
    global _CURRENT_SETTINGS
    _CURRENT_SETTINGS = settings
