from datetime import date as date_type
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.analytics import (
    AnalyticsDaily,
    AnalyticsProduct,
)
from app.models.failed_job import FailedJob
from app.models.order import Order, OrderStatus
from app.models.order_item import OrderItem
from app.models.product import Product, ProductStatus
from app.models.product_variant import ProductVariant


def current_stockout_rate(
    db: Session,
) -> float:
    total = db.scalar(
        select(func.count())
        .select_from(ProductVariant)
    ) or 0

    if total == 0:
        return 0.0

    zero_stock = db.scalar(
        select(func.count())
        .select_from(ProductVariant)
        .where(
            ProductVariant.stock == 0
        )
    ) or 0

    return round(
        zero_stock / total,
        4,
    )


def recompute_from_raw(
    db: Session,
) -> dict:
    """
    Rebuild analytics aggregates from raw business tables.

    Used by the periodic Celery rollup as a reconciliation
    safety net.
    """

    daily_raw = db.execute(
        select(
            func.date(
                Order.placed_at
            ).label("day"),
            func.count(Order.id),
            func.coalesce(
                func.sum(Order.total),
                0,
            ),
        )
        .where(
            Order.status
            == OrderStatus.COMPLETED
        )
        .group_by(
            func.date(Order.placed_at)
        )
    ).all()

    for (
        day,
        orders_count,
        revenue,
    ) in daily_raw:

        row = db.get(
            AnalyticsDaily,
            day,
        )

        if row is None:
            row = AnalyticsDaily(
                date=day,
            )
            db.add(row)

        row.orders = orders_count
        row.revenue = Decimal(
            revenue
        )

    published_raw = db.execute(
        select(
            func.date(
                Product.published_at
            ).label("day"),
            func.count(Product.id),
        )
        .where(
            Product.status
            == ProductStatus.PUBLISHED,
            Product.published_at.isnot(None),
        )
        .group_by(
            func.date(
                Product.published_at
            )
        )
    ).all()

    for day, count in published_raw:

        row = db.get(
            AnalyticsDaily,
            day,
        )

        if row is None:
            row = AnalyticsDaily(
                date=day,
            )
            db.add(row)

        row.products_published = count

    db.flush()

    product_raw = db.execute(
        select(
            OrderItem.variant_id,
            func.sum(OrderItem.qty),
            func.sum(
                OrderItem.qty
                * OrderItem.unit_price
            ),
        )
        .join(
            Order,
            Order.id == OrderItem.order_id,
        )
        .where(
            Order.status
            == OrderStatus.COMPLETED
        )
        .group_by(
            OrderItem.variant_id
        )
    ).all()

    variant_ids = [
        row[0]
        for row in product_raw
    ]

    variant_to_product = {}

    if variant_ids:
        variant_to_product = {
            variant.id: variant.product_id
            for variant in db.scalars(
                select(ProductVariant)
                .where(
                    ProductVariant.id.in_(
                        variant_ids
                    )
                )
            )
        }

    product_totals: dict = {}

    for (
        variant_id,
        units,
        revenue,
    ) in product_raw:

        product_id = (
            variant_to_product.get(
                variant_id
            )
        )

        if product_id is None:
            continue

        units_sold, existing_revenue = (
            product_totals.get(
                product_id,
                (
                    0,
                    Decimal("0"),
                ),
            )
        )

        product_totals[
            product_id
        ] = (
            units_sold + int(units),
            existing_revenue
            + Decimal(revenue),
        )

    for (
        product_id,
        (
            units_sold,
            revenue,
        ),
    ) in product_totals.items():

        row = db.get(
            AnalyticsProduct,
            product_id,
        )

        if row is None:
            row = AnalyticsProduct(
                product_id=product_id,
            )
            db.add(row)

        row.units_sold = units_sold
        row.revenue = revenue

    db.commit()

    return {
        "days_updated": len(
            daily_raw
        ),
        "products_updated": len(
            product_totals
        ),
    }