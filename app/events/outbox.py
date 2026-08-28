# ENQUEUE - builds envelope + adds OutboxEvent to SAME DB session
from typing import Any

from sqlalchemy.orm import Session

from app.events.envelope import build_envelope
from app.models.outbox_event import OutboxEvent


def enqueue(
    db: Session,
    *,
    event_type: str,
    data: dict[str, Any],
    correlation_id: str,
) -> OutboxEvent:
    """
    Add a domain event to the transactional outbox.

    Important:
    This function does NOT commit.

    The caller must commit the business change and this outbox row
    together in the same database transaction.
    """

    envelope = build_envelope(
        event_type=event_type,
        data=data,
        correlation_id=correlation_id,
    )

    outbox_event = OutboxEvent(
        event_id=envelope.event_id,
        event_type=envelope.event_type,
        payload=envelope.to_dict(),
        correlation_id=envelope.correlation_id,
    )

    db.add(outbox_event)

    return outbox_event
