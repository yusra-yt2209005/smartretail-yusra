import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import (
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
)
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.order_status_history import OrderStatusHistory
from app.models.product import Product, ProductStatus
from app.models.product_variant import ProductVariant
from app.models.user import User
from app.schemas.order import OrderCreate


def get_order(
    db: Session,
    order_id: uuid.UUID,
    user: User,
) -> Order:
    """
    Fetch an order with its line items.

    Customers may only see their own orders.
    """

    order = db.scalar(
        select(Order)
        .options(
            selectinload(Order.items)
        )
        .where(
            Order.id == order_id
        )
    )

    if order is None:
        raise NotFoundError(
            "Order",
            order_id,
        )

    # Keep this simple for Week 2:
    # the customer who created the order may read it.
    #
    # If your existing User model has an ADMIN role and you already
    # support admin access elsewhere, you can extend this later.
    if order.customer_id != user.id:
        raise ForbiddenError(
            "You do not have access to this order"
        )

    return order


def build_order(
    db: Session,
    user: User,
    data: OrderCreate,
    idempotency_key: str,
) -> Order:
    """
    Create the initial PLACED order.

    Prices come from the database, never from the client.
    SKU and price are snapshotted into OrderItem.
    """

    # ---------------------------------------------------------
    # Database-level fallback idempotency check
    # ---------------------------------------------------------

    existing = db.scalar(
        select(Order)
        .options(
            selectinload(Order.items)
        )
        .where(
            Order.customer_id == user.id,
            Order.idempotency_key == idempotency_key,
        )
    )

    if existing is not None:
        return existing

    subtotal = Decimal("0.00")

    prepared_items = []

    for requested_item in data.items:

        # Get the real variant + its product.
        row = db.execute(
            select(
                ProductVariant,
                Product,
            )
            .join(
                Product,
                ProductVariant.product_id
                == Product.id,
            )
            .where(
                ProductVariant.id
                == requested_item.variant_id
            )
        ).first()

        if row is None:
            raise ValidationFailedError(
                [
                    (
                        "Variant "
                        f"'{requested_item.variant_id}' "
                        "was not found"
                    )
                ]
            )

        variant, product = row

        # Orders should only contain products that are actually
        # available in the published catalog.
        if (
            product.status
            != ProductStatus.PUBLISHED
        ):
            raise ValidationFailedError(
                [
                    (
                        f"Product '{product.id}' "
                        "is not published"
                    )
                ]
            )

        if not variant.is_active:
            raise ValidationFailedError(
                [
                    (
                        f"Variant '{variant.id}' "
                        "is inactive"
                    )
                ]
            )

        line_total = (
            Decimal(variant.price)
            * requested_item.qty
        )

        subtotal += line_total

        prepared_items.append(
            (
                variant,
                requested_item.qty,
            )
        )

    # ---------------------------------------------------------
    # Create Order
    # ---------------------------------------------------------

    order = Order(
        customer_id=user.id,
        status=OrderStatus.PLACED,
        subtotal=subtotal,
        total=subtotal,
        idempotency_key=idempotency_key,
    )

    db.add(order)

    # Flush gives us order.id without committing yet.
    db.flush()

    # ---------------------------------------------------------
    # Create OrderItems
    # ---------------------------------------------------------

    for variant, qty in prepared_items:

        db.add(
            OrderItem(
                order_id=order.id,
                variant_id=variant.id,

                # Snapshot values so historical orders don't change
                # if the merchant later changes SKU/price.
                sku_snapshot=variant.sku,
                unit_price=variant.price,

                qty=qty,
            )
        )

    # Record initial lifecycle state.
    db.add(
        OrderStatusHistory(
            order_id=order.id,
            from_status=None,
            to_status=OrderStatus.PLACED,
            actor="customer",
            reason=None,
        )
    )

    db.commit()

    # Reload items so OrderOut can serialize them.
    return get_order(
        db,
        order.id,
        user,
    )