import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.product import Product


class ProductVariant(TimestampMixin, Base):
    """
    A Product is the general catalog item, such as "T-shirt".

    A ProductVariant is the specific sellable item, such as
    "T-shirt, red, M". Price and stock therefore belong here rather
    than on Product.

    Week 2's concurrency-safe inventory reservation also operates
    directly on variant rows.
    """

    __tablename__ = "product_variants"

    __table_args__ = (
        CheckConstraint(
            "price > 0",
            name="ck_product_variants_price_positive",
        ),
        CheckConstraint(
            "stock >= 0",
            name="ck_product_variants_stock_nonnegative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sku: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    # Numeric(10, 2), not float, because money should use exact
    # base-10 decimal arithmetic.
    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    stock: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # Flexible variant properties such as:
    # {"color": "red", "size": "M"}
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
    )

    product: Mapped["Product"] = relationship(
        "Product",
        back_populates="variants",
    )