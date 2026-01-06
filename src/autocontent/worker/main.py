from __future__ import annotations

from autocontent.infrastructure.celery_app import celery_app


def run() -> None:
    celery_app.worker_main(argv=["worker", "-l", "info"])
