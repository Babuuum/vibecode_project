from __future__ import annotations

from celery import Celery

from autocontent.config import Settings

settings = Settings()

celery_app = Celery(
    "autocontent",
    broker=settings.resolved_celery_broker_url,
    backend=settings.resolved_celery_result_backend,
)

celery_app.conf.update(task_default_queue="default", beat_schedule={})

# Register tasks
try:
    from autocontent.worker import tasks as _worker_tasks  # noqa: F401
except Exception:
    pass
