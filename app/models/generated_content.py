from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    String,
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
from app.models.mixins import (
    TimestampMixin,
)


class GeneratedContentType(
    str,
    enum.Enum,
):
    """
    Types of AI-generated merchant content.
    """

    DESCRIPTION = "description"
    SEO = "seo"
    FAQ = "faq"


class GeneratedContent(
    TimestampMixin,
    Base,
):
    """
    Persisted AI-generated content for one product.

    Keeping the model and prompt version makes each generation
    reviewable and reproducible.
    """

    __tablename__ = "generated_content"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "products.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    content_type: Mapped[
        GeneratedContentType
    ] = mapped_column(
        "type",
        Enum(
            GeneratedContentType,
            name="generated_content_type",
            values_callable=lambda enum_cls: [
                member.value
                for member in enum_cls
            ],
        ),
        nullable=False,
        index=True,
    )

    content: Mapped[
        dict[str, Any]
    ] = mapped_column(
        JSONB,
        nullable=False,
    )

    model: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    prompt_version: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    accepted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )