import json
import logging
import signal

from confluent_kafka import Consumer

from app.core.config import settings
from app.db.session import SessionLocal
from app.events.handlers import (
    process_event,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


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

            # We explicitly commit offsets only
            # after successful processing.
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

            try:
                envelope = json.loads(
                    message.value().decode(
                        "utf-8"
                    )
                )

                with SessionLocal() as db:
                    process_event(
                        db,
                        envelope,
                    )

                # Only move Kafka's offset AFTER
                # database processing succeeded.
                consumer.commit(
                    message=message,
                    asynchronous=False,
                )

                logger.info(
                    "Processed Kafka event %s (%s)",
                    envelope.get(
                        "event_id"
                    ),
                    envelope.get(
                        "event_type"
                    ),
                )

            except Exception:
                logger.exception(
                    "Failed to process Kafka event"
                )

                # Do NOT commit this message's
                # offset on processing failure.

    finally:
        consumer.close()


if __name__ == "__main__":
    run()