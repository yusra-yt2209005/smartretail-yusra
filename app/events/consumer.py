import json
import logging
import signal

from confluent_kafka import Consumer

from app.core.config import settings
from app.core.correlation import (
    reset_correlation_id,
    set_correlation_id,
)
from app.core.logging import configure_logging
from app.core.metrics import (
    EVENTS_CONSUMED_TOTAL,
    EVENTS_FAILED_TOTAL,
)
from app.db.session import SessionLocal
from app.events.handlers import process_event


configure_logging()

logger = logging.getLogger(
    "smartretail.kafka.consumer"
)


def build_consumer() -> Consumer:
    """
    Create the Kafka analytics consumer.
    """

    return Consumer(
        {
            "bootstrap.servers": (
                settings.kafka_bootstrap_servers
            ),
            "group.id": (
                settings.kafka_consumer_group
            ),
            "auto.offset.reset": "earliest",

            # Kafka should not automatically advance offsets.
            # We commit only after processing succeeds.
            "enable.auto.commit": False,
        }
    )


def run() -> None:
    consumer = build_consumer()

    consumer.subscribe(
        [
            settings.kafka_events_topic
        ]
    )

    logger.info(
        "Kafka consumer subscribed to %s",
        settings.kafka_events_topic,
    )

    running = True

    def stop(
        *_args,
    ) -> None:
        nonlocal running
        running = False

    signal.signal(
        signal.SIGTERM,
        stop,
    )

    signal.signal(
        signal.SIGINT,
        stop,
    )

    try:
        while running:
            message = consumer.poll(
                timeout=1.0
            )

            if message is None:
                continue

            if message.error():
                logger.warning(
                    "Kafka consumer error: %s",
                    message.error(),
                )
                continue

            # Defaults let us record a useful failure metric even if
            # decoding/parsing fails before we can read event_type.
            envelope = None
            event_type = "unknown"
            token = None

            try:
                envelope = json.loads(
                    message.value().decode("utf-8")
                )

                event_type = envelope.get(
                    "event_type",
                    "unknown",
                )

                correlation_id = envelope.get(
                    "correlation_id",
                    "-",
                )

                token = set_correlation_id(
                    correlation_id
                )

                logger.info(
                    "Received Kafka event %s (%s)",
                    envelope.get("event_id"),
                    event_type,
                )

                with SessionLocal() as db:
                    applied = process_event(
                        db,
                        envelope,
                    )

                # Commit the Kafka offset ONLY after database
                # processing succeeds or the event is safely
                # identified as a duplicate.
                consumer.commit(
                    message=message,
                    asynchronous=False,
                )

                # Count every Kafka message that was handled
                # successfully, including safe duplicate deliveries.
                EVENTS_CONSUMED_TOTAL.labels(
                    event_type=event_type,
                ).inc()

                logger.info(
                    "%s Kafka event %s (%s)",
                    (
                        "Applied"
                        if applied
                        else "Skipped duplicate"
                    ),
                    envelope.get("event_id"),
                    event_type,
                )

            except Exception:
                # A duplicate is not a failure because process_event()
                # handles it normally and returns False. This counter
                # therefore represents actual processing failures.
                EVENTS_FAILED_TOTAL.labels(
                    event_type=event_type,
                ).inc()

                logger.exception(
                    "Failed to process Kafka message"
                )

                # IMPORTANT:
                # Do not commit the Kafka offset here.
                # Kafka may redeliver the message, and processed_events
                # keeps that retry safe.

            finally:
                if token is not None:
                    reset_correlation_id(
                        token
                    )

    finally:
        consumer.close()


if __name__ == "__main__":
    run()
