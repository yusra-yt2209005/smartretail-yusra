import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.product import Product


class ContentChunk(TimestampMixin, Base):
    """
    Searchable text generated from a product during publishing.

    Week 2 creates the text chunks.
    Week 4 can later generate embeddings from them.
    """

    __tablename__ = "content_chunks"

    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "chunk_index",
            name="uq_content_chunks_product_chunk_index",
        ),
    )

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

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    text_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    embedded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    product: Mapped["Product"] = relationship(
        "Product",
        back_populates="content_chunks",
    )