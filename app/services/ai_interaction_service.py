from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.correlation import (
    get_correlation_id,
)
from app.models.ai_interaction import (
    AIInteraction,
)


def record_ai_interaction(
    db: Session,
    *,
    question: str,
    intent: str,
    answer: str,
    refused: bool,
    status: str,
    prompt_version: str | None,
    model: str | None,
    product_ids: list[str],
    variant_ids: list[str],
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: float = 0.0,
    correlation_id: str | None = None,
) -> AIInteraction:
    """
    Persist one AI assistant interaction.

    Streaming callers may supply the correlation ID captured before
    the response stream begins. Non-streaming callers continue using
    the current request correlation ID automatically.
    """

    resolved_correlation_id = (
        correlation_id
        if correlation_id is not None
        else get_correlation_id()
    )

    interaction = AIInteraction(
        correlation_id=resolved_correlation_id,
        question=question,
        intent=intent,
        answer=answer,
        refused=refused,
        status=status,
        prompt_version=prompt_version,
        model=model,
        product_ids=product_ids,
        variant_ids=variant_ids,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=round(
            latency_ms,
            2,
        ),
    )

    db.add(
        interaction
    )

    db.commit()

    db.refresh(
        interaction
    )

    return interaction