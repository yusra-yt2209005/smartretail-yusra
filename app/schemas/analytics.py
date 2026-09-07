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

class AIIntentBreakdown(BaseModel):
    discovery: int = 0
    comparison: int = 0
    guidance: int = 0
    merchant_content: int = 0


class AIAnalyticsOut(BaseModel):
    questions_asked: int
    answered: int
    refused: int

    intent_breakdown: AIIntentBreakdown

    average_latency_ms: float
    p95_latency_ms: float

    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int

    conversions_after_ai: int
    conversion_rate: float