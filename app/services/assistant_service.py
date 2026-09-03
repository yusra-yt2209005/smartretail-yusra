from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.ai.llm import (
    LLMProvider,
    get_llm_provider,
)
from app.ai.prompts import (
    DISCOVERY_PROMPT_VERSION,
    build_discovery_prompt,
)
from app.schemas.assistant import (
    AssistantCitation,
    AssistantResponse,
)
from app.services.search_service import (
    search_products,
)


NO_RESULTS_MESSAGE = (
    "I couldn't find any currently available products "
    "that match your request."
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
        citations=citations,
        refused=False,
        prompt_version=(
            DISCOVERY_PROMPT_VERSION
        ),
        model=result.model,
    )