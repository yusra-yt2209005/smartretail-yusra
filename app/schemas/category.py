import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):  #POST /categories
    name: str = Field(min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None
    order_index: int = Field(default=0, ge=0)


class CategoryUpdate(BaseModel): #PATCH /categories/{id}
    """
    PATCH-style partial update.

    Every field is optional. The service layer should use
    model_dump(exclude_unset=True) so only fields actually sent by the
    client are changed.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: uuid.UUID | None = None
    order_index: int | None = Field(default=None, ge=0)


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    order_index: int
    created_at: datetime
    updated_at: datetime