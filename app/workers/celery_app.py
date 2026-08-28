from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

from celery.signals import setup_logging

from app.core.logging import configure_logging

@setup_logging.connect
def setup_celery_logging(
    **kwargs,
):
    configure_logging()
    
celery_app = Celery(
    "smartretail",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.notifications",
        "app.workers.tasks.analytics",
        "app.workers.tasks.outbox_publisher",
    ]
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

        "publish-outbox-every-5-seconds": {
            "task": (
                "app.workers.tasks.outbox_publisher."
                "run_outbox_publish"
            ),
            "schedule": 5.0,
        },
    },
)