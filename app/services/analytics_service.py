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

from dataclasses import dataclass
from app.models.analytics import AnalyticsDaily, AnalyticsProduct
from app.models.failed_job import FailedJob
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.models.product_variant import ProductVariant

@dataclass
class AnalyticsSummary:
    total_products_published: int
    orders_over_time: list[dict]
    revenue_trend: list[dict]
    most_popular_products: list[dict]
    average_order_value: Decimal
    inventory_stockout_rate: float
    failed_jobs_count: int



def get_summary(
    db: Session,
    *,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
    top_n: int = 10,
) -> AnalyticsSummary:
    """
    Read analytics from pre-aggregated tables.

    start_date/end_date filter the daily order/revenue series.
    Product popularity is all-time.
    """

    daily_stmt = select(
        AnalyticsDaily
    ).order_by(
        AnalyticsDaily.date
    )

    if start_date is not None:
        daily_stmt = daily_stmt.where(
            AnalyticsDaily.date >= start_date
        )

    if end_date is not None:
        daily_stmt = daily_stmt.where(
            AnalyticsDaily.date <= end_date
        )

    daily_rows = list(
        db.scalars(
            daily_stmt
        )
    )

    orders_over_time = [
        {
            "date": row.date,
            "orders": row.orders,
        }
        for row in daily_rows
    ]

    revenue_trend = [
        {
            "date": row.date,
            "revenue": Decimal(
                row.revenue
            ),
        }
        for row in daily_rows
    ]

    total_orders = sum(
        row.orders
        for row in daily_rows
    )

    total_revenue = sum(
        (
            Decimal(row.revenue)
            for row in daily_rows
        ),
        Decimal("0"),
    )

    average_order_value = (
        total_revenue / total_orders
        if total_orders
        else Decimal("0")
    )

    total_products_published = (
        db.scalar(
            select(
                func.coalesce(
                    func.sum(
                        AnalyticsDaily.products_published
                    ),
                    0,
                )
            )
        )
        or 0
    )

    popular_rows = list(
        db.scalars(
            select(
                AnalyticsProduct
            )
            .order_by(
                AnalyticsProduct.units_sold.desc()
            )
            .limit(top_n)
        )
    )

    product_ids = [
        row.product_id
        for row in popular_rows
    ]

    titles: dict = {}

    if product_ids:
        titles = {
            product.id: product.title
            for product in db.scalars(
                select(Product).where(
                    Product.id.in_(
                        product_ids
                    )
                )
            )
        }

    most_popular_products = [
        {
            "product_id": row.product_id,
            "title": titles.get(
                row.product_id,
                "(deleted product)",
            ),
            "units_sold": row.units_sold,
            "revenue": Decimal(
                row.revenue
            ),
        }
        for row in popular_rows
    ]

    failed_jobs_count = (
        db.scalar(
            select(
                func.count()
            ).select_from(
                FailedJob
            )
        )
        or 0
    )

    return AnalyticsSummary(
        total_products_published=int(
            total_products_published
        ),
        orders_over_time=orders_over_time,
        revenue_trend=revenue_trend,
        most_popular_products=(
            most_popular_products
        ),
        average_order_value=(
            average_order_value
        ),
        inventory_stockout_rate=(
            current_stockout_rate(db)
        ),
        failed_jobs_count=(
            failed_jobs_count
        ),
    )

def reconcile_day(
    db: Session,
    day: date_type,
) -> dict:
    """
    Compare one day's analytics projection against raw source tables.

    This function deliberately reads raw tables because its purpose
    is to detect projection drift.
    """

    aggregate = db.get(
        AnalyticsDaily,
        day,
    )

    aggregated_orders = (
        aggregate.orders
        if aggregate
        else 0
    )

    aggregated_revenue = (
        Decimal(aggregate.revenue)
        if aggregate
        else Decimal("0")
    )

    aggregated_products = (
        aggregate.products_published
        if aggregate
        else 0
    )

    raw_order_result = db.execute(
        select(
            func.count(Order.id),
            func.coalesce(
                func.sum(Order.total),
                0,
            ),
        ).where(
            Order.status
            == OrderStatus.COMPLETED,
            func.date(
                Order.placed_at
            )
            == day,
        )
    ).one()

    raw_orders = int(
        raw_order_result[0]
    )

    raw_revenue = Decimal(
        raw_order_result[1]
    )

    raw_products = (
        db.scalar(
            select(
                func.count(Product.id)
            ).where(
                Product.published_at.isnot(
                    None
                ),
                func.date(
                    Product.published_at
                )
                == day,
            )
        )
        or 0
    )

    order_drift = (
        aggregated_orders
        - raw_orders
    )

    revenue_drift = (
        aggregated_revenue
        - raw_revenue
    )

    product_drift = (
        aggregated_products
        - raw_products
    )

    return {
        "date": day,
        "aggregated": {
            "orders": aggregated_orders,
            "revenue": aggregated_revenue,
            "products_published": (
                aggregated_products
            ),
        },
        "raw": {
            "orders": raw_orders,
            "revenue": raw_revenue,
            "products_published": (
                raw_products
            ),
        },
        "drift": {
            "orders": order_drift,
            "revenue": revenue_drift,
            "products_published": (
                product_drift
            ),
        },
        "matches": (
            order_drift == 0
            and revenue_drift == 0
            and product_drift == 0
        ),
    }




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