import enum
import uuid

from sqlalchemy import Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class UserRole(str, enum.Enum):
    CUSTOMER = "customer"
    MERCHANT = "merchant"
    ADMIN = "admin"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    # UUID primary keys instead of auto-increment integers.
    # UUIDs do not expose sequential record numbers and work well
    # when identifiers may eventually be generated across services.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Email is unique because it is the user's login identity.
    # The index makes lookups by email efficient during authentication.
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    # Never store the user's plaintext password.
    # Authentication stores and compares a password hash instead.
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=UserRole.CUSTOMER,
    )

    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
    )

    # ORM relationship, not a database column.
    # The actual foreign key will live on Product.merchant_id.
    products = relationship(
        "Product",
        back_populates="merchant",
    )