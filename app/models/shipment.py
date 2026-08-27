import enum
import uuid

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class ShipmentStatus(str, enum.Enum):
    CREATED = "created"
    DISPATCHED = "dispatched"
    DELIVERED = "delivered"


class Shipment(TimestampMixin, Base):
    __tablename__ = "shipments"

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

    status: Mapped[ShipmentStatus] = mapped_column(
        Enum(
            ShipmentStatus,
            name="shipment_status",
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        default=ShipmentStatus.CREATED,
        nullable=False,
    )

    address: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )