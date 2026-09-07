from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.orm import Session

from app.models.ai_interaction import (
    AIInteraction,
)
from app.models.order import Order
from app.models.order_item import OrderItem


def get_ai_analytics(
    db: Session,
) -> dict:
    """
    Return aggregate AI usage and conversion analytics.
    """

    # ---------------------------------------------------------
    # Basic counts
    # ---------------------------------------------------------

    questions_asked = (
        db.scalar(
            select(
                func.count(
                    AIInteraction.id
                )
            )
        )
        or 0
    )

    refused = (
        db.scalar(
            select(
                func.count(
                    AIInteraction.id
                )
            ).where(
                AIInteraction.refused.is_(
                    True
                )
            )
        )
        or 0
    )

    answered = (
        db.scalar(
            select(
                func.count(
                    AIInteraction.id
                )
            ).where(
                AIInteraction.refused.is_(
                    False
                ),
                AIInteraction.status
                == "completed",
            )
        )
        or 0
    )

    # ---------------------------------------------------------
    # Intent breakdown
    # ---------------------------------------------------------

    intent_rows = db.execute(
        select(
            AIInteraction.intent,
            func.count(
                AIInteraction.id
            ),
        ).group_by(
            AIInteraction.intent
        )
    ).all()

    intent_breakdown = {
        "discovery": 0,
        "comparison": 0,
        "guidance": 0,
        "merchant_content": 0,
    }

    for intent, count in intent_rows:
        if intent in intent_breakdown:
            intent_breakdown[
                intent
            ] = int(count)

    # ---------------------------------------------------------
    # Latency
    # ---------------------------------------------------------

    average_latency = (
        db.scalar(
            select(
                func.avg(
                    AIInteraction.latency_ms
                )
            )
        )
        or 0.0
    )

    p95_latency = (
        db.scalar(
            select(
                func.percentile_cont(
                    0.95
                ).within_group(
                    AIInteraction.latency_ms
                )
            )
        )
        or 0.0
    )

    # ---------------------------------------------------------
    # Tokens
    # ---------------------------------------------------------

    input_tokens = (
        db.scalar(
            select(
                func.coalesce(
                    func.sum(
                        AIInteraction
                        .input_tokens
                    ),
                    0,
                )
            )
        )
        or 0
    )

    output_tokens = (
        db.scalar(
            select(
                func.coalesce(
                    func.sum(
                        AIInteraction
                        .output_tokens
                    ),
                    0,
                )
            )
        )
        or 0
    )

    # ---------------------------------------------------------
    # Conversion after AI
    #
    # A conversion means:
    # - same authenticated customer
    # - order happened after AI interaction
    # - purchased variant was one of the variants cited by AI
    # ---------------------------------------------------------

    interactions = list(
        db.scalars(
            select(
                AIInteraction
            ).where(
                AIInteraction.user_id.isnot(
                    None
                ),
                AIInteraction.refused.is_(
                    False
                ),
            )
        )
    )

    converted_interaction_ids = set()

    for interaction in interactions:
        recommended_variants = {
            str(variant_id)
            for variant_id
            in (
                interaction.variant_ids
                or []
            )
        }

        if not recommended_variants:
            continue

        purchased_variants = db.execute(
            select(
                OrderItem.variant_id
            )
            .join(
                Order,
                Order.id
                == OrderItem.order_id,
            )
            .where(
                Order.customer_id
                == interaction.user_id,
                Order.placed_at
                >= interaction.created_at,
            )
        ).scalars().all()

        if any(
            str(variant_id)
            in recommended_variants
            for variant_id
            in purchased_variants
        ):
            converted_interaction_ids.add(
                interaction.id
            )

    conversion_base = len(
        interactions
    )

    conversions = len(
        converted_interaction_ids
    )

    conversion_rate = (
        conversions
        / conversion_base
        if conversion_base
        else 0.0
    )

    return {
        "questions_asked": int(
            questions_asked
        ),
        "answered": int(
            answered
        ),
        "refused": int(
            refused
        ),
        "intent_breakdown": (
            intent_breakdown
        ),
        "average_latency_ms": float(
            average_latency
        ),
        "p95_latency_ms": float(
            p95_latency
        ),
        "total_input_tokens": int(
            input_tokens
        ),
        "total_output_tokens": int(
            output_tokens
        ),
        "total_tokens": int(
            input_tokens
            + output_tokens
        ),
        "conversions_after_ai": (
            conversions
        ),
        "conversion_rate": (
            round(
                conversion_rate,
                4,
            )
        ),
    }