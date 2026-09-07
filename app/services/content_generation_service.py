from __future__ import annotations
import time
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.llm import (
    LLMProvider,
    get_llm_provider,
)
from app.ai.prompts import (
    DESCRIPTION_PROMPT_VERSION,
    FAQ_PROMPT_VERSION,
    SEO_PROMPT_VERSION,
    build_description_prompt,
    build_faq_prompt,
    build_faq_repair_prompt,
    build_seo_prompt,
)
from app.core.exceptions import (
    AIOutputValidationError,
)
from app.models.product import Product
from app.models.user import User
from app.schemas.generated_content import (
    FAQResponse,
    SEOResponse,
)
from app.services import product_service
from app.models.generated_content import (
    GeneratedContent,
    GeneratedContentType,
)
from app.core.metrics import (
    AI_FAILURES_TOTAL,
    AI_REQUEST_LATENCY_SECONDS,
    AI_REQUESTS_TOTAL,
    AI_TOKENS_TOTAL,
)
from app.services.ai_interaction_service import (
    record_ai_interaction,
)

def get_owned_product(
    db: Session,
    *,
    product_id: uuid.UUID,
    user: User,
) -> Product:
    """
    Load the product and verify that the authenticated merchant
    is allowed to generate content for it.
    """

    product = product_service.get_product(
        db,
        product_id,
    )

    product_service.assert_can_edit(
        product,
        user,
    )

    return product

def persist_generated_content(
    db: Session,
    *,
    product: Product,
    content_type: GeneratedContentType,
    content: dict[str, Any],
    model: str,
    prompt_version: str,
) -> GeneratedContent:
    """
    Save one merchant AI generation against its product.
    """

    generated = GeneratedContent(
        product_id=product.id,
        content_type=content_type,
        content=content,
        model=model,
        prompt_version=prompt_version,
        accepted=False,
    )

    db.add(
        generated
    )

    db.commit()

    db.refresh(
        generated
    )

    return generated

def _record_merchant_ai_interaction(
    db: Session,
    *,
    product: Product,
    user_id: uuid.UUID,
    correlation_id: str | None,
    content_type: str,
    answer: str,
    model: str,
    prompt_version: str,
    input_tokens: int,
    output_tokens: int,
    started_at: float,
    status: str = "completed",
) -> None:
    """
    Record merchant AI generation for analytics and Prometheus.
    """

    latency_ms = (
        time.perf_counter()
        - started_at
    ) * 1000

    record_ai_interaction(
        db,
        user_id=user_id,
        correlation_id=correlation_id,
        question=(
            f"Generate {content_type} "
            f"for product {product.id}"
        ),
        intent="merchant_content",
        answer=answer,
        refused=False,
        status=status,
        prompt_version=prompt_version,
        model=model,
        product_ids=[
            str(product.id)
        ],
        variant_ids=[
            str(variant.id)
            for variant
            in product.variants
        ],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )

    AI_REQUESTS_TOTAL.labels(
        intent="merchant_content",
        refused="false",
    ).inc()

    AI_REQUEST_LATENCY_SECONDS.labels(
        intent="merchant_content",
    ).observe(
        latency_ms / 1000
    )

    AI_TOKENS_TOTAL.labels(
        type="input",
    ).inc(
        input_tokens
    )

    AI_TOKENS_TOTAL.labels(
        type="output",
    ).inc(
        output_tokens
    )

    if status != "completed":
        AI_FAILURES_TOTAL.labels(
            intent="merchant_content",
        ).inc()

def build_product_context(
    product: Product,
) -> str:
    """
    Convert one real SmartRetail product into grounded LLM context.

    The model receives catalog facts only; it does not query the
    database itself.
    """

    variant_blocks: list[str] = []

    for variant in sorted(
        product.variants,
        key=lambda item: item.sku,
    ):
        attributes = json.dumps(
            variant.attributes or {},
            sort_keys=True,
        )

        variant_blocks.append(
            (
                f"SKU: {variant.sku}; "
                f"Price: {variant.price}; "
                f"Stock: {variant.stock}; "
                f"Active: {variant.is_active}; "
                f"Attributes: {attributes}"
            )
        )

    variants_text = (
        "\n".join(variant_blocks)
        if variant_blocks
        else "No variants"
    )

    category_text = (
        str(product.category_id)
        if product.category_id is not None
        else "Uncategorized"
    )

    return (
        f"Product ID: {product.id}\n"
        f"Title: {product.title.strip()}\n"
        f"Category ID: {category_text}\n"
        f"Status: {product.status.value}\n"
        f"Description: {product.description.strip()}\n"
        f"Variants:\n{variants_text}"
    )

async def stream_description(
    *,
    product: Product,
    llm: LLMProvider | None = None,
    db: Session | None = None,
    user_id: uuid.UUID | None = None,
    correlation_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Stream, persist, and record analytics for a generated
    product description.
    """

    started_at = time.perf_counter()

    product_context = build_product_context(
        product
    )

    system_prompt, user_prompt = (
        build_description_prompt(
            product_context
        )
    )

    provider = (
        llm
        if llm is not None
        else get_llm_provider()
    )

    answer_parts: list[str] = []

    input_tokens = 0
    output_tokens = 0

    # ---------------------------------------------------------
    # Stream actual LLM output
    # ---------------------------------------------------------

    async for event in provider.stream(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    ):
        if event.done:
            input_tokens = (
                event.input_tokens
                or 0
            )

            output_tokens = (
                event.output_tokens
                or 0
            )

            break

        if event.text:
            answer_parts.append(
                event.text
            )

            yield {
                "type": "text",
                "text": event.text,
            }

    # IMPORTANT:
    # Build the completed description BEFORE persistence
    # or analytics tries to use it.
    description = "".join(
        answer_parts
    )

    generated_content_id = None

    # ---------------------------------------------------------
    # Persist successful generated content
    # ---------------------------------------------------------

    if db is not None:
        generated = (
            persist_generated_content(
                db,
                product=product,
                content_type=(
                    GeneratedContentType
                    .DESCRIPTION
                ),
                content={
                    "text": description,
                },
                model=provider.model_name,
                prompt_version=(
                    DESCRIPTION_PROMPT_VERSION
                ),
            )
        )

        generated_content_id = str(
            generated.id
        )

    # ---------------------------------------------------------
    # Record AI analytics + Prometheus metrics
    # ---------------------------------------------------------

    if (
        db is not None
        and user_id is not None
    ):
        _record_merchant_ai_interaction(
            db,
            product=product,
            user_id=user_id,
            correlation_id=correlation_id,
            content_type="description",
            answer=description,
            model=provider.model_name,
            prompt_version=(
                DESCRIPTION_PROMPT_VERSION
            ),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            started_at=started_at,
        )

    # ---------------------------------------------------------
    # Final metadata
    # ---------------------------------------------------------

    yield {
        "type": "metadata",
        "product_id": str(
            product.id
        ),
        "generated_content_id": (
            generated_content_id
        ),
        "content_type": "description",
        "prompt_version": (
            DESCRIPTION_PROMPT_VERSION
        ),
        "model": provider.model_name,
    }

    # ---------------------------------------------------------
    # Terminal SSE event
    # ---------------------------------------------------------

    yield {
        "type": "done",
        "status": "completed",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }

async def stream_seo(
    *,
    product: Product,
    llm: LLMProvider | None = None,
    db: Session | None = None,
    user_id: uuid.UUID | None = None,
    correlation_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Generate, validate, stream, and persist SEO content.
    """
    started_at = time.perf_counter()
    product_context = build_product_context(
        product
    )

    system_prompt, user_prompt = (
        build_seo_prompt(
            product_context
        )
    )

    provider = (
        llm
        if llm is not None
        else get_llm_provider()
    )

    answer_parts: list[str] = []

    input_tokens = 0
    output_tokens = 0

    chunk_index = 0
    characters_received = 0

    async for event in provider.stream(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    ):
        if event.done:
            input_tokens = (
                event.input_tokens
                or 0
            )

            output_tokens = (
                event.output_tokens
                or 0
            )

            break

        if event.text:
            answer_parts.append(
                event.text
            )

            chunk_index += 1

            characters_received += len(
                event.text
            )

            yield {
                "type": "progress",
                "stage": "generating",
                "chunk_index": chunk_index,
                "characters_received": (
                    characters_received
                ),
            }

    raw_output = "".join(
        answer_parts
    )

    try:
        validated = (
            SEOResponse.model_validate_json(
                raw_output
            )
        )

    except ValidationError:
        yield {
            "type": "error",
            "code": "ai_output_invalid",
            "message": (
                "The AI provider returned "
                "invalid SEO JSON."
            ),
        }

        yield {
            "type": "done",
            "status": "failed",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

        return

    seo_content = validated.model_dump(
        mode="json"
    )

    generated_content_id = None

    if db is not None:
        generated = (
            persist_generated_content(
                db,
                product=product,
                content_type=(
                    GeneratedContentType.SEO
                ),
                content=seo_content,
                model=provider.model_name,
                prompt_version=(
                    SEO_PROMPT_VERSION
                ),
            )
        )

        generated_content_id = str(
            generated.id
        )



    if (
        db is not None
        and user_id is not None
    ):
        _record_merchant_ai_interaction(
            db,
            product=product,
            user_id=user_id,
            correlation_id=correlation_id,
            content_type="seo",
            answer=json.dumps(
                seo_content,
                sort_keys=True,
            ),
            model=provider.model_name,
            prompt_version=(
                SEO_PROMPT_VERSION
            ),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            started_at=started_at,
        )

    yield {
        "type": "seo",
        "seo": seo_content,
    }

    yield {
        "type": "metadata",
        "product_id": str(
            product.id
        ),
        "generated_content_id": (
            generated_content_id
        ),
        "content_type": "seo",
        "prompt_version": (
            SEO_PROMPT_VERSION
        ),
        "model": provider.model_name,
    }

    yield {
        "type": "done",
        "status": "completed",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }

async def generate_faq_with_repair(
    *,
    product: Product,
    count: int,
    llm: LLMProvider | None = None,
) -> tuple[
    FAQResponse,
    str,
    int,
    int,
]:
    """
    Generate structured FAQ JSON.

    Attempt 1:
        generate -> Pydantic validate

    If invalid:
        repair once -> validate again

    If the repair is also invalid:
        raise a clean 502-style application error.
    """

    product_context = build_product_context(
        product
    )

    provider = (
        llm
        if llm is not None
        else get_llm_provider()
    )

    system_prompt, user_prompt = (
        build_faq_prompt(
            product_context,
            count=count,
        )
    )

    first_result = await provider.generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    try:
        faq = (
            FAQResponse.model_validate_json(
                first_result.text
            )
        )

        if len(faq.faqs) != count:
            raise ValueError(
                f"Expected {count} FAQs but "
                f"received {len(faq.faqs)}."
            )

        return (
            faq,
            provider.model_name,
            first_result.input_tokens,
            first_result.output_tokens,
        )

    except (
        ValidationError,
        ValueError,
    ) as first_error:
        repair_system, repair_user = (
            build_faq_repair_prompt(
                product_context,
                count=count,
                invalid_output=(
                    first_result.text
                ),
                validation_error=str(
                    first_error
                ),
            )
        )

    # Exactly one repair attempt.
    repair_result = await provider.generate(
        system_prompt=repair_system,
        user_prompt=repair_user,
    )

    try:
        faq = (
            FAQResponse.model_validate_json(
                repair_result.text
            )
        )

        if len(faq.faqs) != count:
            raise ValueError(
                f"Expected {count} FAQs but "
                f"received {len(faq.faqs)}."
            )

    except (
        ValidationError,
        ValueError,
    ) as second_error:
        raise AIOutputValidationError(
            (
                "FAQ output was invalid after "
                "one repair attempt."
            )
        ) from second_error

    return (
        faq,
        provider.model_name,
        (
            first_result.input_tokens
            + repair_result.input_tokens
        ),
        (
            first_result.output_tokens
            + repair_result.output_tokens
        ),
    )

async def stream_faq(
    *,
    product: Product,
    count: int,
    llm: LLMProvider | None = None,
    db: Session | None = None,
    user_id: uuid.UUID | None = None,
    correlation_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Stream FAQ generation progress.

    The raw LLM JSON is collected internally and validated before
    FAQ items are exposed.

    If attempt 1 is invalid, exactly one repair attempt is made.
    """
    started_at = time.perf_counter()
    product_context = build_product_context(
        product
    )

    provider = (
        llm
        if llm is not None
        else get_llm_provider()
    )

    # =========================================================
    # Attempt 1
    # =========================================================

    system_prompt, user_prompt = (
        build_faq_prompt(
            product_context,
            count=count,
        )
    )

    first_parts: list[str] = []

    total_input_tokens = 0
    total_output_tokens = 0

    chunk_index = 0
    characters_received = 0

    async for event in provider.stream(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    ):
        if event.done:
            total_input_tokens += (
                event.input_tokens
                or 0
            )

            total_output_tokens += (
                event.output_tokens
                or 0
            )

            break

        if event.text:
            first_parts.append(
                event.text
            )

            chunk_index += 1
            characters_received += len(
                event.text
            )

            yield {
                "type": "progress",
                "stage": "generating",
                "attempt": 1,
                "chunk_index": chunk_index,
                "characters_received": (
                    characters_received
                ),
            }

    first_output = "".join(
        first_parts
    )

    first_error: Exception | None = None

    try:
        faq = (
            FAQResponse.model_validate_json(
                first_output
            )
        )

        if len(faq.faqs) != count:
            raise ValueError(
                f"Expected {count} FAQs but "
                f"received {len(faq.faqs)}."
            )

    except (
        ValidationError,
        ValueError,
    ) as exc:
        first_error = exc

    # =========================================================
    # Attempt 2 — exactly one repair
    # =========================================================

    if first_error is not None:
        yield {
            "type": "repair",
            "attempt": 2,
            "message": (
                "The first FAQ output was invalid. "
                "Trying one repair."
            ),
        }

        repair_system, repair_user = (
            build_faq_repair_prompt(
                product_context,
                count=count,
                invalid_output=first_output,
                validation_error=str(
                    first_error
                ),
            )
        )

        repair_parts: list[str] = []

        chunk_index = 0
        characters_received = 0

        async for event in provider.stream(
            system_prompt=repair_system,
            user_prompt=repair_user,
        ):
            if event.done:
                total_input_tokens += (
                    event.input_tokens
                    or 0
                )

                total_output_tokens += (
                    event.output_tokens
                    or 0
                )

                break

            if event.text:
                repair_parts.append(
                    event.text
                )

                chunk_index += 1
                characters_received += len(
                    event.text
                )

                yield {
                    "type": "progress",
                    "stage": "repairing",
                    "attempt": 2,
                    "chunk_index": (
                        chunk_index
                    ),
                    "characters_received": (
                        characters_received
                    ),
                }

        repair_output = "".join(
            repair_parts
        )

        try:
            faq = (
                FAQResponse.model_validate_json(
                    repair_output
                )
            )

            if len(faq.faqs) != count:
                raise ValueError(
                    f"Expected {count} FAQs but "
                    f"received {len(faq.faqs)}."
                )

        except (
            ValidationError,
            ValueError,
        ):
            yield {
                "type": "error",
                "code": "ai_output_invalid",
                "message": (
                    "FAQ output was invalid after "
                    "one repair attempt."
                ),
            }

            yield {
                "type": "done",
                "status": "failed",
                "input_tokens": (
                    total_input_tokens
                ),
                "output_tokens": (
                    total_output_tokens
                ),
            }

            return

    # =========================================================
    # Valid structured output
    # =========================================================
    faq_content = faq.model_dump(
        mode="json"
    )

    generated_content_id = None

    # ---------------------------------------------------------
    # Persist the validated FAQ content
    # ---------------------------------------------------------

    if db is not None:
        generated = (
            persist_generated_content(
                db,
                product=product,
                content_type=(
                    GeneratedContentType.FAQ
                ),
                content=faq_content,
                model=provider.model_name,
                prompt_version=(
                    FAQ_PROMPT_VERSION
                ),
            )
        )

        generated_content_id = str(
            generated.id
        )

    # ---------------------------------------------------------
    # Record merchant AI analytics + Prometheus metrics
    # ---------------------------------------------------------

    if (
        db is not None
        and user_id is not None
    ):
        _record_merchant_ai_interaction(
            db,
            product=product,
            user_id=user_id,
            correlation_id=correlation_id,
            content_type="faq",
            answer=json.dumps(
                faq_content,
                sort_keys=True,
            ),
            model=provider.model_name,
            prompt_version=(
                FAQ_PROMPT_VERSION
            ),
            input_tokens=(
                total_input_tokens
            ),
            output_tokens=(
                total_output_tokens
            ),
            started_at=started_at,
        )

    # ---------------------------------------------------------
    # Send only validated FAQ items to the client
    # ---------------------------------------------------------

    for item in faq.faqs:
        yield {
            "type": "faq",
            "faq": item.model_dump(
                mode="json"
            ),
        }

    # ---------------------------------------------------------
    # Final metadata
    # ---------------------------------------------------------

    yield {
        "type": "metadata",
        "product_id": str(
            product.id
        ),
        "generated_content_id": (
            generated_content_id
        ),
        "content_type": "faq",
        "prompt_version": (
            FAQ_PROMPT_VERSION
        ),
        "model": provider.model_name,
        "count": len(
            faq.faqs
        ),
    }

    # ---------------------------------------------------------
    # Terminal SSE event
    # ---------------------------------------------------------

    yield {
        "type": "done",
        "status": "completed",
        "input_tokens": (
            total_input_tokens
        ),
        "output_tokens": (
            total_output_tokens
        ),
    }