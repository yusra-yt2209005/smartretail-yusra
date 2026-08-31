import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class OrdersDailyPoint(BaseModel):
    date: date
    orders: int


class RevenueDailyPoint(BaseModel):
    date: date
    revenue: Decimal


class PopularProductOut(BaseModel):
    product_id: uuid.UUID
    title: str
    units_sold: int
    revenue: Decimal


class AnalyticsSummaryOut(BaseModel):
    total_products_published: int
    orders_over_time: list[OrdersDailyPoint]
    revenue_trend: list[RevenueDailyPoint]
    most_popular_products: list[PopularProductOut]
    average_order_value: Decimal
    inventory_stockout_rate: float
    failed_jobs_count: int


class ReconciliationValues(BaseModel):
    orders: int
    revenue: Decimal
    products_published: int


class ReconciliationDrift(BaseModel):
    orders: int
    revenue: Decimal
    products_published: int


class AnalyticsReconciliationOut(BaseModel):
    date: date
    aggregated: ReconciliationValues
    raw: ReconciliationValues
    drift: ReconciliationDrift
    matches: bool