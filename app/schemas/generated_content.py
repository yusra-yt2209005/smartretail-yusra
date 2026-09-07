from pydantic import (
    BaseModel,
    Field,
)


class FAQItem(BaseModel):
    """
    One generated FAQ question/answer pair.
    """

    question: str = Field(
        min_length=1,
        max_length=300,
    )

    answer: str = Field(
        min_length=1,
        max_length=2000,
    )


class FAQResponse(BaseModel):
    """
    Structured FAQ output returned by the LLM.
    """

    faqs: list[FAQItem] = Field(
        min_length=1,
        max_length=20,
    )


class SEOResponse(BaseModel):
    """
    Structured SEO content for one product.
    """

    title: str = Field(
        min_length=1,
        max_length=120,
    )

    meta_description: str = Field(
        min_length=1,
        max_length=300,
    )

class FAQGenerationRequest(BaseModel):
    """
    Controls how many FAQs the merchant wants.
    """

    count: int = Field(
        default=5,
        ge=1,
        le=10,
    )