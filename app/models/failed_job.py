import uuid

from sqlalchemy import String, Text, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class FailedJob(TimestampMixin, Base):
    __tablename__ = "failed_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    task_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    task_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    payload: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    error: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    attempts: Mapped[int] = mapped_column(
        Integer, 
        nullable=False, 
        default=1
    )