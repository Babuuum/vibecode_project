from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings with sensible defaults."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="allow")

    app_name: str = "AutoContent TG"
    environment: str = "development"
    api_host: str = "0.0.0.0"
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
    sentry_dsn: str = Field(default="", description="Sentry DSN (optional).")
    sqlalchemy_echo: bool = False
    llm_provider: str = "mock"
    llm_api_key: str = ""
    llm_base_url: str = "http://llm:8000"
    llm_mode: str = Field(default="economy", description="economy|normal")
    drafts_per_day: int = 20
    publishes_per_day: int = 20
    sources_limit: int = 10
    fetch_interval_min: int = 10
    source_fail_threshold: int = 3
    max_generate_per_fetch: int = 5
    generate_lock_ttl: int = 60
    duplicate_window_days: int = 7

    @property
    def llm_max_tokens(self) -> int:
        return 128 if self.llm_mode == "economy" else 512

    @property
    def resolved_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def resolved_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url
