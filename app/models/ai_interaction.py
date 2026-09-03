import uuid

from sqlalchemy import (
    Boolean,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import (
    JSONB,
    UUID,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.db.base import Base
from app.models.mixins import TimestampMixin


class AIInteraction(
    TimestampMixin,
    Base,
):
    """
    One customer interaction with the SmartRetail AI assistant.

    Stores enough information for auditing and Week 5 AI analytics.
    """

    __tablename__ = "ai_interactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    correlation_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    question: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    intent: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    answer: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    refused: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="completed",
        index=True,
    )

    prompt_version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    product_ids: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )

    variant_ids: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )

    input_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    output_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    latency_ms: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )