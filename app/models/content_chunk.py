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


from pgvector.sqlalchemy import Vector

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)

from app.core.config import settings

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

    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "product_variants.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "categories.id",
            ondelete="SET NULL",
        ),
        nullable=True,
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

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.vector_dimensions),
        nullable=True,
    )


    price: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    status: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        index=True,
    )

    available: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        index=True,
    )

    in_stock: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
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