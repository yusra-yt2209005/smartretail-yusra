import enum
import uuid
from decimal import Decimal

from sqlalchemy import Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class PaymentStatus(str, enum.Enum):
    AUTHORIZED = "authorized"
    FAILED = "failed"
    REFUNDED = "refunded"


class Payment(TimestampMixin, Base):
    """
    Stores a simulated payment authorization result.

    The order_id + idempotency_key pair prevents the same order's
    payment authorization from being recorded twice if Temporal
    retries the Activity later.
    """

    __tablename__ = "payments"

    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "idempotency_key",
            name="uq_payments_order_id_idempotency_key",
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

    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    status: Mapped[PaymentStatus] = mapped_column(
        Enum(
            PaymentStatus,
            name="payment_status",
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        nullable=False,
    )

    provider_ref: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )