from __future__ import annotations

from celery import Celery

from autocontent.config import Settings

try:
    import sentry_sdk
except Exception:  # pragma: no cover
    sentry_sdk = None

settings = Settings()
if sentry_sdk and settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)

celery_app = Celery(
    "autocontent",
    broker=settings.resolved_celery_broker_url,
    backend=settings.resolved_celery_result_backend,
)

celery_app.conf.update(
    task_default_queue="default",
    beat_schedule={
        "fetch-all-sources": {
            "task": "fetch_all_sources",
            "schedule": settings.fetch_interval_min * 60,
        },
        "publish-due-drafts": {
            "task": "publish_due_drafts",
            "schedule": 120,
        }
    },
)

# Register tasks
try:
    from autocontent.worker import tasks as _worker_tasks  # noqa: F401
except Exception:
    pass
