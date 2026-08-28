"""
Alembic's env.py needs `Base.metadata` to already know about every table
when it autogenerates a migration. SQLAlchemy only registers a model with
Base when the *module defining it* has been imported somewhere. Importing
all model modules here -- and importing this package from alembic/env.py --
is what makes that happen in one place instead of scattering imports.
"""
from sqlalchemy import delete, select

from app.models.category import Category  # noqa: F401
from app.models.product import Product, ProductStatus  # noqa: F401
from app.models.product_media import ProductMedia  # noqa: F401
from app.models.product_variant import ProductVariant  # noqa: F401
from app.models.user import User, UserRole  # noqa: F401
from app.models.content_chunk import ContentChunk  # noqa: F401

from app.models.order import Order, OrderStatus  # noqa: F401
from app.models.order_item import OrderItem  # noqa: F401
from app.models.order_status_history import OrderStatusHistory  # noqa: F401
from app.models.payment import Payment, PaymentStatus  # noqa: F401

from app.models.shipment import Shipment, ShipmentStatus  # noqa: F401

from app.models.inventory_reservation import InventoryReservation  # noqa: F401
from app.models.inventory_reservation import ReservationStatus  # noqa: F401

from app.services import inventory_service
from app.services.payment_service import PaymentAuthorizer


from app.models.failed_job import FailedJob  # noqa: F401
from app.models.notification import Notification  # noqa: F401

from app.models.analytics import (
    AnalyticsDaily,
    AnalyticsProduct,
)  # noqa: F401

from app.models.outbox_event import OutboxEvent  # noqa: F401

