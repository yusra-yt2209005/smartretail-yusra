from __future__ import annotations
import re 
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
    GUIDANCE_PROMPT_VERSION,
    build_comparison_prompt,
    build_discovery_prompt,
    build_guidance_prompt,
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

GUIDANCE_KEYWORDS = (
    "should i buy",
    "should i choose",
    "what should i buy",
    "which should i buy",
    "which one should i buy",
    "which one should i choose",
    "help me choose",
    "best for me",
    "recommend for me",
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

    Intent routing is deterministic and does not require
    an additional LLM call.
    """

    normalized = (
        f" {question.strip().lower()} "
    )

    if any(
        keyword in normalized
        for keyword in COMPARISON_KEYWORDS
    ):
        return AssistantIntent.COMPARISON

    if any(
        keyword in normalized
        for keyword in GUIDANCE_KEYWORDS
    ):
        return AssistantIntent.GUIDANCE

    return AssistantIntent.DISCOVERY


def build_retrieval_query(
    question: str,
    intent: AssistantIntent,
) -> str:
    """
    Remove intent-related wording that does not help catalog retrieval.

    The original customer question is still preserved for the LLM prompt.
    """

    query = question.strip()

    if intent == AssistantIntent.GUIDANCE:
        removable_phrases = (
            "which one should i buy",
            "which should i buy",
            "what should i buy",
            "should i buy",
            "which one should i choose",
            "should i choose",
            "help me choose",
        )

        lowered = query.lower()

        for phrase in removable_phrases:
            lowered = lowered.replace(
                phrase,
                " ",
            )

        # Remove punctuation left behind by the original question.
        lowered = re.sub(
            r"[^\w\s-]",
            " ",
            lowered,
        )

        query = " ".join(
            lowered.split()
        )

        words = query.split()

        while (
            words
            and words[0]
            in {
                "which",
                "what",
            }
        ):
            words.pop(0)

        query = " ".join(words)

    return query or question.strip()

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

    if (
        intent
        == AssistantIntent.GUIDANCE
    ):
        return await ask_guidance(
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

async def ask_guidance(
    db: Session,
    *,
    question: str,
    top_k: int = 5,
    llm: LLMProvider | None = None,
) -> AssistantResponse:
    """
    Give grounded buying guidance using currently buyable
    products retrieved from the catalog.
    """

    question = question.strip()

    retrieval_query = build_retrieval_query(
        question,
        AssistantIntent.GUIDANCE,
    )

    products = search_products(
        db,
        query=retrieval_query,
        top_k=top_k,
        include_context=True,
    )

    # Buying advice must never be invented when retrieval
    # returns no valid products.
    if not products:
        return AssistantResponse(
            question=question,
            answer=(
                "I couldn't find any currently available "
                "products that match your needs."
            ),
            intent=AssistantIntent.GUIDANCE,
            citations=[],
            refused=True,
            prompt_version=(
                GUIDANCE_PROMPT_VERSION
            ),
            model=None,
        )

    prompt_products = (
        _build_prompt_products(
            products
        )
    )

    system_prompt, user_prompt = (
        build_guidance_prompt(
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
        intent=AssistantIntent.GUIDANCE,
        citations=citations,
        refused=False,
        prompt_version=(
            GUIDANCE_PROMPT_VERSION
        ),
        model=result.model,
    )