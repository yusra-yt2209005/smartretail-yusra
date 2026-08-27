from celery import Celery
from celery.schedules import crontab

from app.core.config import settings


celery_app = Celery(
    "smartretail",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.notifications",
        "app.workers.tasks.analytics",
    ],
)


celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    timezone="UTC",
    enable_utc=True,

    beat_schedule={
        "analytics-rollup-every-5-minutes": {
            "task": (
                "app.workers.tasks.analytics."
                "run_analytics_rollup"
            ),
            "schedule": crontab(
                minute="*/5"
            ),
        },
    },
)