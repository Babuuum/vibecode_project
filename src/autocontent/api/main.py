from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from autocontent.api.routes import api_router
from autocontent.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.state.settings = settings
    app.include_router(api_router)
    return app


app = create_app()


def run() -> None:
    settings = Settings()
    uvicorn.run(
        "autocontent.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.reload,
        log_level=settings.log_level,
    )
