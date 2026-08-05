import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.product import Product


class ProductMedia(TimestampMixin, Base):
    """
    Stores a reference to a product media asset, such as an image URL.

    Week 1 stores only metadata; no real image transcoding is performed.
    In Week 2, the publishing workflow can simulate media processing by
    changing `processed` from False to True.
    """

    __tablename__ = "product_media"

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

    url: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    order_index: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    processed: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    product: Mapped["Product"] = relationship(
        "Product",
        back_populates="media",
    )