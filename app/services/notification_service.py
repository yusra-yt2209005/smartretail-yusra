import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.notification import Notification
from app.models.order import Order


def create_order_notification(
    order_id: str,
    event_type: str,
) -> Notification:
    """
    Create one simulated notification for an order event.

    The actual notification is just a database row for Week 3.
    No email or SMS integration is required.

    Idempotency:
    the same order + event uses the same deduplication_key,
    so a Celery retry does not create duplicate notifications.
    """

    order_uuid = uuid.UUID(order_id)

    deduplication_key = (
        f"order:{order_uuid}:{event_type}"
    )

    with SessionLocal() as db:
        order = db.get(
            Order,
            order_uuid,
        )

        if order is None:
            raise ValueError(
                f"Order {order_id} not found"
            )

        existing = db.scalar(
            select(Notification).where(
                Notification.deduplication_key
                == deduplication_key
            )
        )

        if existing is not None:
            return existing

        notification = Notification(
            user_id=order.customer_id,
            notification_type=event_type,
            message=(
                f"Order {order_id} event: "
                f"{event_type}"
            ),
            payload={
                "order_id": order_id,
                "status": order.status.value,
            },
            deduplication_key=deduplication_key,
        )

        db.add(notification)
        db.commit()
        db.refresh(notification)

        return notification