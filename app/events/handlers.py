import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analytics import (
    AnalyticsDaily,
    AnalyticsProduct,
)
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product_variant import ProductVariant


def process_event(
    db: Session,
    envelope: dict,
) -> bool:
    """
    Apply one Kafka event to the analytics aggregates.

    Idempotency is added in task 3.5.
    """

    event_type = envelope["event_type"]
    data = envelope["data"]

    if event_type == "product.published":
        _apply_product_published(
            db,
            data,
        )

    elif event_type == "order.confirmed":
        _apply_order_confirmed(
            db,
            data,
        )

    elif event_type == "inventory.reserved":
        _apply_inventory_reserved(
            db,
            data,
        )

    # The remaining events are valid domain events,
    # but currently do not feed an analytics aggregate:
    #
    # order.placed
    # payment.succeeded
    # shipment.created
    # refund.processed

    db.commit()

    return True


def _daily_row(
    db: Session,
    day,
) -> AnalyticsDaily:
    """
    Get the aggregate row for one day,
    creating it if it does not exist.
    """

    row = db.get(
        AnalyticsDaily,
        day,
    )

    if row is None:
        row = AnalyticsDaily(
            date=day,
        )

        db.add(row)
        db.flush()

    return row


def _apply_product_published(
    db: Session,
    data: dict,
) -> None:
    published_at = datetime.fromisoformat(
        data["published_at"]
    )

    day = published_at.date()

    row = _daily_row(
        db,
        day,
    )

    row.products_published += 1


def _apply_order_confirmed(
    db: Session,
    data: dict,
) -> None:
    """
    Update daily order/revenue aggregates and
    all-time per-product sales aggregates.
    """

    order_id = uuid.UUID(
        data["order_id"]
    )

    order = db.get(
        Order,
        order_id,
    )

    if order is None:
        raise ValueError(
            f"Order {order_id} not found"
        )

    day = order.placed_at.date()

    daily = _daily_row(
        db,
        day,
    )

    daily.orders += 1

    daily.revenue = (
        Decimal(daily.revenue)
        + Decimal(order.total)
    )

    items = list(
        db.scalars(
            select(OrderItem).where(
                OrderItem.order_id
                == order_id
            )
        )
    )

    if not items:
        return

    variant_ids = [
        item.variant_id
        for item in items
    ]

    variants = {
        variant.id: variant.product_id
        for variant in db.scalars(
            select(ProductVariant).where(
                ProductVariant.id.in_(
                    variant_ids
                )
            )
        )
    }

    for item in items:
        product_id = variants.get(
            item.variant_id
        )

        if product_id is None:
            continue

        product_row = db.get(
            AnalyticsProduct,
            product_id,
        )

        if product_row is None:
            product_row = AnalyticsProduct(
                product_id=product_id,
                units_sold=0,
                revenue=Decimal("0"),
            )

            db.add(product_row)
            db.flush()

        product_row.units_sold += (
            item.qty
        )

        product_row.revenue = (
            Decimal(product_row.revenue)
            + (
                Decimal(item.unit_price)
                * item.qty
            )
        )


def _apply_inventory_reserved(
    db: Session,
    data: dict,
) -> None:
    """
    Count a stockout when a reservation leaves
    a variant with exactly zero stock.
    """

    if not data.get(
        "stockout",
        False,
    ):
        return

    reserved_at = datetime.fromisoformat(
        data["reserved_at"]
    )

    day = reserved_at.date()

    row = _daily_row(
        db,
        day,
    )

    row.stockouts += 1