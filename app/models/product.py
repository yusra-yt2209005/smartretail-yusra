import enum
import uuid
from typing import TYPE_CHECKING
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.product_media import ProductMedia
    from app.models.product_variant import ProductVariant
    from app.models.user import User
    from app.models.content_chunk import ContentChunk


class ProductStatus(str, enum.Enum):
    """
    Product lifecycle states.

    """

    DRAFT = "draft"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    PUBLISH_FAILED = "publish_failed"
    INACTIVE = "inactive"


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # We intentionally do not cascade merchant deletion to products.
    # Merchants should normally be deactivated rather than deleted.
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # Nullable allows a merchant to save an incomplete draft before
    # choosing a category. Publishing validation can require one later.
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id"),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    status: Mapped[ProductStatus] = mapped_column(
        Enum(
            ProductStatus,
            name="product_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ProductStatus.DRAFT,
        index=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
    )

    # Python-side ORM relationship to the merchant that owns the product.
    merchant: Mapped["User"] = relationship(
        "User",
        back_populates="products",
    )

    category: Mapped["Category | None"] = relationship(
        "Category",
        back_populates="products",
    )

    # ProductVariant and ProductMedia are composition relationships:
    # these rows have no useful meaning without their parent Product.
    variants: Mapped[list["ProductVariant"]] = relationship(
        "ProductVariant",
        back_populates="product",
        cascade="all, delete-orphan",
    )

    media: Mapped[list["ProductMedia"]] = relationship(
        "ProductMedia",
        back_populates="product",
        cascade="all, delete-orphan",
    )

    content_chunks: Mapped[list["ContentChunk"]] = relationship(
    "ContentChunk",
    back_populates="product",
    cascade="all, delete-orphan",
    )