from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from src.autocontent.api.routes import api_router
from src.autocontent.config import Settings

try:
    import sentry_sdk
except Exception:  # pragma: no cover
    sentry_sdk = None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    if sentry_sdk and settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.state.settings = settings
    app.include_router(api_router)
    return app


app = create_app()


def run() -> None:
    settings = Settings()
    uvicorn.run(
        "src.autocontent.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.reload,
        log_level=settings.log_level,
    )
