import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outbox_event import OutboxEvent


_producer = None


def get_producer():
    """
    Lazily create and reuse one Kafka Producer per process.
    """

    global _producer

    if _producer is None:
        from confluent_kafka import Producer

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
    batch_size: int = 100,
) -> int:
    """
    Publish unpublished outbox events to Kafka.

    An outbox row is marked published only after Kafka confirms
    successful delivery.

    Returns the number of events successfully published.
    """

    rows = list(
        db.scalars(
            select(OutboxEvent)
            .where(
                OutboxEvent.published_at.is_(None)
            )
            .order_by(OutboxEvent.created_at)
            .limit(batch_size)
        )
    )

    if not rows:
        return 0

    producer = get_producer()

    published_ids = []

    def on_delivery(
        error,
        message,
        row_id,
    ):
        if error is None:
            published_ids.append(row_id)

    for row in rows:
        try:
            producer.produce(
                topic=settings.kafka_events_topic,

                # Using event_type as the Kafka key keeps
                # related event types consistently partitioned.
                key=row.event_type.encode("utf-8"),

                value=json.dumps(
                    row.payload
                ).encode("utf-8"),

                callback=lambda error, message, row_id=row.id: (
                    on_delivery(
                        error,
                        message,
                        row_id,
                    )
                ),
            )

        except BufferError:
            # Local producer queue is temporarily full.
            # Leave remaining rows unpublished so they can
            # be retried by the next outbox-publisher run.
            break

    # Wait for queued Kafka deliveries/callbacks.
    producer.flush(
        timeout=10,
    )

    if published_ids:
        now = datetime.now(
            timezone.utc
        )

        db.query(
            OutboxEvent
        ).filter(
            OutboxEvent.id.in_(
                published_ids
            )
        ).update(
            {
                "published_at": now,
            },
            synchronize_session=False,
        )

        db.commit()

    return len(
        published_ids
    )