from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.ai.llm import (
    LLMProvider,
    get_llm_provider,
)

from app.schemas.assistant import (
    AssistantCitation,
    AssistantIntent,
    AssistantResponse,
)
from app.services.search_service import (
    search_products,
)

from app.ai.prompts import (
    COMPARISON_PROMPT_VERSION,
    DISCOVERY_PROMPT_VERSION,
    build_comparison_prompt,
    build_discovery_prompt,
)


NO_RESULTS_MESSAGE = (
    "I couldn't find any currently available products "
    "that match your request."
)

COMPARISON_KEYWORDS = (
    "compare",
    "comparison",
    " vs ",
    " versus ",
    "difference between",
    "differences between",
)


def _build_prompt_products(
    products: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convert search results into grounded catalog data for the prompt.

    Only real values returned by retrieval are passed to the LLM.
    """

    prompt_products: list[
        dict[str, Any]
    ] = []

    for product in products:
        prompt_products.append(
            {
                "product_id": str(
                    product["product_id"]
                ),
                "variant_id": str(
                    product["variant_id"]
                ),
                "title": product[
                    "title"
                ],
                "category_id": (
                    str(
                        product[
                            "category_id"
                        ]
                    )
                    if product[
                        "category_id"
                    ]
                    is not None
                    else None
                ),
                "price": str(
                    product["price"]
                ),
                "similarity": product[
                    "similarity"
                ],
                "catalog_text": product.get(
                    "context_text"
                ),
            }
        )

    return prompt_products


def _build_citations(
    products: list[dict[str, Any]],
) -> list[AssistantCitation]:
    """
    Build citations from actual retrieval results.

    Citations are application-generated rather than trusted
    from LLM output.
    """

    return [
        AssistantCitation(
            product_id=product[
                "product_id"
            ],
            variant_id=product[
                "variant_id"
            ],
            title=product["title"],
            price=product["price"],
        )
        for product in products
    ]

def detect_intent(
    question: str,
) -> AssistantIntent:
    """
    Determine the assistant intent from the customer's question.

    Comparison detection is deterministic and does not require
    another LLM call.
    """

    normalized = (
        f" {question.strip().lower()} "
    )

    if any(
        keyword in normalized
        for keyword in COMPARISON_KEYWORDS
    ):
        return AssistantIntent.COMPARISON

    return AssistantIntent.DISCOVERY

async def ask_discovery(
    db: Session,
    *,
    question: str,
    top_k: int = 5,
    llm: LLMProvider | None = None,
) -> AssistantResponse:
    """
    Answer a product-discovery question using retrieval-augmented
    generation.

    Retrieval happens first. If no valid buyable products are found,
    return a refusal without calling the LLM.
    """

    question = question.strip()

    products = search_products(
        db,
        query=question,
        top_k=top_k,
        include_context=True,
    )

    # ---------------------------------------------------------
    # Important grounding rule:
    # never ask the LLM to invent an answer when retrieval failed.
    # ---------------------------------------------------------

    if not products:
        return AssistantResponse(
            question=question,
            answer=NO_RESULTS_MESSAGE,
            intent=AssistantIntent.DISCOVERY,
            citations=[],
            refused=True,
            prompt_version=(
                DISCOVERY_PROMPT_VERSION
            ),
            model=None,
        )

    prompt_products = (
        _build_prompt_products(
            products
        )
    )

    system_prompt, user_prompt = (
        build_discovery_prompt(
            question,
            prompt_products,
        )
    )

    provider = (
        llm
        if llm is not None
        else get_llm_provider()
    )

    result = await provider.generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    citations = _build_citations(
        products
    )

    return AssistantResponse(
        question=question,
        answer=result.text,
        intent=AssistantIntent.DISCOVERY,
        citations=citations,
        refused=False,
        prompt_version=(
            DISCOVERY_PROMPT_VERSION
        ),
        model=result.model,
    )

async def ask_comparison(
    db: Session,
    *,
    question: str,
    top_k: int = 5,
    llm: LLMProvider | None = None,
) -> AssistantResponse:
    """
    Compare products using natural-language retrieval.

    The customer supplies product names or descriptions rather
    than internal product UUIDs.
    """

    question = question.strip()

    products = search_products(
        db,
        query=question,
        top_k=top_k,
        include_context=True,
    )

    # A comparison requires at least two valid products.
    if len(products) < 2:
        return AssistantResponse(
            question=question,
            answer=(
                "I couldn't find at least two "
                "currently available products "
                "to compare."
            ),
            intent=(
                AssistantIntent.COMPARISON
            ),
            citations=[],
            refused=True,
            prompt_version=(
                COMPARISON_PROMPT_VERSION
            ),
            model=None,
        )

    # For this comparison task, use the two strongest
    # retrieval matches.
    compared_products = products[:2]

    prompt_products = (
        _build_prompt_products(
            compared_products
        )
    )

    system_prompt, user_prompt = (
        build_comparison_prompt(
            question,
            prompt_products,
        )
    )

    provider = (
        llm
        if llm is not None
        else get_llm_provider()
    )

    result = await provider.generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    citations = _build_citations(
        compared_products
    )

    return AssistantResponse(
        question=question,
        answer=result.text,
        intent=(
            AssistantIntent.COMPARISON
        ),
        citations=citations,
        refused=False,
        prompt_version=(
            COMPARISON_PROMPT_VERSION
        ),
        model=result.model,
    )

async def ask_assistant(
    db: Session,
    *,
    question: str,
    top_k: int = 5,
    llm: LLMProvider | None = None,
) -> AssistantResponse:
    """
    Route a customer question to the correct assistant behavior.
    """

    intent = detect_intent(
        question
    )

    if (
        intent
        == AssistantIntent.COMPARISON
    ):
        return await ask_comparison(
            db,
            question=question,
            top_k=top_k,
            llm=llm,
        )

    return await ask_discovery(
        db,
        question=question,
        top_k=top_k,
        llm=llm,
    )