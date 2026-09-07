import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


EVENT_ENVELOPE_VERSION = 1


@dataclass
class EventEnvelope:
    """
    Standard envelope used by every SmartRetail domain event.

    `data` contains event-specific identifiers/details.
    The remaining fields are common to every event.
    """

    event_type: str
    data: dict[str, Any]
    correlation_id: str

    event_id: uuid.UUID = field(
        default_factory=uuid.uuid4
    )

    version: int = EVENT_ENVELOPE_VERSION

    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)

        # Convert values that JSON cannot serialize directly.
        result["event_id"] = str(
            self.event_id
        )

        result["occurred_at"] = (
            self.occurred_at.isoformat()
        )

        return result


def build_envelope(
    event_type: str,
    data: dict[str, Any],
    correlation_id: str,
) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        data=data,
        correlation_id=correlation_id,
    )