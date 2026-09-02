import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"

    __table_args__ = (
        UniqueConstraint(
            "deduplication_key",
            name="uq_notifications_deduplication_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    notification_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    payload: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    deduplication_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )