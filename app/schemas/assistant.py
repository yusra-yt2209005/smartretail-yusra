import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class AssistantRequest(BaseModel):
    """
    Customer request to the SmartRetail AI assistant.
    """

    question: str = Field(
        min_length=1,
        max_length=500,
    )

    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
    )


class AssistantCitation(BaseModel):
    """
    Real catalog product referenced by the assistant.
    """

    product_id: uuid.UUID
    variant_id: uuid.UUID
    title: str
    price: Decimal


class AssistantResponse(BaseModel):
    """
    Final non-streaming assistant response.
    """

    question: str
    answer: str

    citations: list[
        AssistantCitation
    ] = []

    refused: bool = False

    prompt_version: str | None = None

    model: str | None = None