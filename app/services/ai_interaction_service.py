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
) -> AIInteraction:
    """
    Persist one completed/refused AI assistant interaction.
    """

    interaction = AIInteraction(
        correlation_id=(
            get_correlation_id()
        ),
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