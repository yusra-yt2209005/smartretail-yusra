import uuid
from datetime import date as date_type
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Date,
    ForeignKey,
    Integer,
    Numeric,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalyticsDaily(Base):
    """
    One pre-aggregated row per UTC calendar day.

    Updated later by Kafka events and periodically reconciled
    by the Celery analytics rollup.
    """

    __tablename__ = "analytics_daily"

    date: Mapped[date_type] = mapped_column(
        Date,
        primary_key=True,
    )

    orders: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    revenue: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    stockouts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    products_published: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class AnalyticsProduct(Base):
    """
    All-time per-product aggregate used for popularity/revenue metrics.
    """

    __tablename__ = "analytics_product"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "products.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    units_sold: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    revenue: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )