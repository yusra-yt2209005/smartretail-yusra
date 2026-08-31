import logging

from app.db.session import SessionLocal
from app.services import analytics_service
from app.workers.celery_app import celery_app


logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.tasks.analytics.run_analytics_rollup"
)
def run_analytics_rollup() -> dict:
    """
    Periodically recompute analytics aggregates from raw tables.

    The actual analytics logic lives in analytics_service.
    This Celery task is intentionally a thin wrapper.
    """

    with SessionLocal() as db:
        result = analytics_service.recompute_from_raw(db)

    logger.info(
        "Analytics rollup complete: %s",
        result,
    )

    return result