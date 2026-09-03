import uuid
from decimal import Decimal
from enum import Enum
from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

class AssistantIntent(str, Enum):
    DISCOVERY = "discovery"
    COMPARISON = "comparison"
    GUIDANCE = "guidance"

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

    @field_validator("question")
    @classmethod
    def validate_question(
        cls,
        value: str,
    ) -> str:
        """
        Normalize and reject empty or invalid questions.
        """

        value = value.strip()

        if not value:
            raise ValueError(
                "Question must not be empty."
            )

        if "\x00" in value:
            raise ValueError(
                "Question contains invalid characters."
            )

        return value


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

    intent: AssistantIntent

    citations: list[
        AssistantCitation
    ] = []

    refused: bool = False

    prompt_version: str | None = None

    model: str | None = None

