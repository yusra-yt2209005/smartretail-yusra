# ProductCreate
# ├── title
# ├── description
# ├── category_id
# ├── variants[]
# │    ├── sku
# │    ├── price
# │    ├── stock
# │    └── attributes
# └── media[]
#      ├── url
#      └── order_index

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.product import ProductStatus


# ---------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------


class VariantCreate(BaseModel):
    """
    Data required to create a product variant.

    Stock belongs to the variant, not the product.
    """

    sku: str = Field(min_length=1, max_length=100)
    price: Decimal = Field(gt=0)
    stock: int = Field(ge=0)
    attributes: dict[str, Any] = Field(default_factory=dict)


class VariantUpdate(BaseModel):
    """
    PATCH-style partial update for an existing variant.

    SKU is intentionally not editable here. If SKU changes are needed
    later, that can be handled explicitly.
    """

    price: Decimal | None = Field(default=None, gt=0)
    stock: int | None = Field(default=None, ge=0)
    attributes: dict[str, Any] | None = None
    is_active: bool | None = None


class VariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    price: Decimal
    stock: int
    attributes: dict[str, Any]
    is_active: bool


# ---------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------


class MediaCreate(BaseModel):
    url: str = Field(min_length=1, max_length=1000)
    order_index: int = Field(default=0, ge=0)


class MediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    order_index: int
    processed: bool


# ---------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------


class ProductCreate(BaseModel):
    """
    Create a product together with at least one variant.

    merchant_id is deliberately absent because ownership comes from the
    authenticated merchant, not from client input.
    """

    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    category_id: uuid.UUID | None = None

    variants: list[VariantCreate] = Field(min_length=1) 
    #   |_ means a product cannot be created with zero variants. 
    # Since stock and price live on variants, a product with no 
    # variants would not be sellable anyway.

    media: list[MediaCreate] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    """
    PATCH-style partial update for product-level fields.

    Variant updates are handled separately so product metadata and
    inventory changes remain clear operations.
    """

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    category_id: uuid.UUID | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    merchant_id: uuid.UUID
    category_id: uuid.UUID | None

    title: str
    description: str
    status: ProductStatus

    created_at: datetime
    updated_at: datetime

    variants: list[VariantOut] = Field(default_factory=list)
    media: list[MediaOut] = Field(default_factory=list)