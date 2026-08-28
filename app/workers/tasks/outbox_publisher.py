import logging

from app.db.session import SessionLocal
from app.events.producer import (
    publish_pending_outbox,
)
from app.workers.celery_app import celery_app


logger = logging.getLogger(__name__)


@celery_app.task(
    name=(
        "app.workers.tasks.outbox_publisher."
        "run_outbox_publish"
    )
)
def run_outbox_publish() -> int:
    """
    Publish pending transactional-outbox events to Kafka.
    """

    with SessionLocal() as db:
        count = publish_pending_outbox(
            db
        )

    if count:
        logger.info(
            "Published %d outbox event(s) to Kafka",
            count,
        )

    return count