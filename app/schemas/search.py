import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """
    Request body for semantic catalog search.
    """

    query: str = Field(
        min_length=1,
        max_length=500,
    )

    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
    )


class SearchResultItem(BaseModel):
    """
    One buyable semantic-search result.
    """

    product_id: uuid.UUID
    variant_id: uuid.UUID

    title: str

    category_id: uuid.UUID | None

    price: Decimal

    similarity: float


class SearchResponse(BaseModel):
    query: str

    items: list[SearchResultItem]

    message: str | None = None