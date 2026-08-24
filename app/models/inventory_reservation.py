import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class ReservationStatus(str, enum.Enum):
    RESERVED = "reserved"
    RELEASED = "released"
    COMMITTED = "committed"


class InventoryReservation(TimestampMixin, Base):
    __tablename__ = "inventory_reservations"

    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "variant_id",
            name="uq_inventory_reservation_order_variant",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "orders.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_variants.id"),
        nullable=False,
        index=True,
    )

    qty: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[ReservationStatus] = mapped_column(
        Enum(
            ReservationStatus,
            name="reservation_status",
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        default=ReservationStatus.RESERVED,
        nullable=False,
    )