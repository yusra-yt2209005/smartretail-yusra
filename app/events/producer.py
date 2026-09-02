import json
import logging
from datetime import UTC, datetime

from confluent_kafka import Producer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.correlation import (
    reset_correlation_id,
    set_correlation_id,
)
from app.models.outbox_event import OutboxEvent


logger = logging.getLogger(
    "smartretail.kafka.producer"
)

_producer: Producer | None = None


def get_producer() -> Producer:
    global _producer

    if _producer is None:
        _producer = Producer(
            {
                "bootstrap.servers": (
                    settings.kafka_bootstrap_servers
                ),
            }
        )

    return _producer


def publish_pending_outbox(
    db: Session,
    *,
    batch_size: int = 100,
) -> int:
    """
    Publish unpublished outbox rows to Kafka.

    Only rows confirmed by Kafka's delivery callback are marked
    published_at.

    If publishing fails, the row remains unpublished so a later
    Celery run can retry it.
    """

    rows = list(
        db.scalars(
            select(OutboxEvent)
            .where(
                OutboxEvent.published_at.is_(
                    None
                )
            )
            .order_by(
                OutboxEvent.created_at
            )
            .limit(batch_size)
        )
    )

    if not rows:
        return 0

    producer = get_producer()

    delivered_ids = []

    def make_delivery_callback(
        *,
        row_id,
        event_id,
        event_type: str,
        correlation_id: str,
    ):
        """
        Create a callback tied to one outbox row.

        Confluent Kafka calls this after delivery succeeds or fails.
        """

        def callback(
            error,
            message,
        ):
            token = set_correlation_id(
                correlation_id
            )

            try:
                if error is not None:
                    logger.error(
                        "Kafka delivery failed for event %s (%s): %s",
                        event_id,
                        event_type,
                        error,
                    )

                    return

                delivered_ids.append(
                    row_id
                )

                logger.info(
                    "Published Kafka event %s (%s)",
                    event_id,
                    event_type,
                )

            finally:
                reset_correlation_id(
                    token
                )

        return callback

    for row in rows:
        token = set_correlation_id(
            row.correlation_id
        )

        try:
            logger.info(
                "Publishing Kafka event %s (%s)",
                row.event_id,
                row.event_type,
            )

            producer.produce(
                topic=(
                    settings.kafka_events_topic
                ),
                key=row.event_type.encode(
                    "utf-8"
                ),
                value=json.dumps(
                    row.payload,
                    default=str,
                ).encode("utf-8"),
                callback=make_delivery_callback(
                    row_id=row.id,
                    event_id=row.event_id,
                    event_type=row.event_type,
                    correlation_id=(
                        row.correlation_id
                    ),
                ),
            )

        except BufferError:
            logger.warning(
                "Kafka producer buffer is full; "
                "remaining events will retry later"
            )

            break

        finally:
            reset_correlation_id(
                token
            )

    # Delivery callbacks run while poll/flush is servicing Kafka.
    producer.flush(
        timeout=10
    )

    if not delivered_ids:
        return 0

    published_at = datetime.now(
        UTC
    )

    published_rows = list(
        db.scalars(
            select(OutboxEvent).where(
                OutboxEvent.id.in_(
                    delivered_ids
                )
            )
        )
    )

    for row in published_rows:
        row.published_at = published_at

    db.commit()

    return len(
        published_rows
    )