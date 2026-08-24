import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.order import OrderStatus


class OrderItemCreate(BaseModel):
    """
    One item requested by the customer when placing an order.
    """

    variant_id: uuid.UUID
    qty: int = Field(gt=0)


class OrderCreate(BaseModel):
    """
    Input payload for creating an order.

    Price and totals are intentionally NOT accepted from the client.
    The backend will calculate them from ProductVariant.price.
    """

    items: list[OrderItemCreate] = Field(
        min_length=1
    )


class OrderItemOut(BaseModel):
    """
    One persisted item returned as part of an order.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: uuid.UUID
    variant_id: uuid.UUID
    sku_snapshot: str
    unit_price: Decimal
    qty: int


class OrderOut(BaseModel):
    """
    API representation of an order.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: uuid.UUID
    customer_id: uuid.UUID
    status: OrderStatus

    subtotal: Decimal
    total: Decimal

    placed_at: datetime
    created_at: datetime
    updated_at: datetime

    items: list[OrderItemOut] = Field(
        default_factory=list
    )