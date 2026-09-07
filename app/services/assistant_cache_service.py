from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from app.ai.llm import LLMProvider
from app.ai.prompts import (
    COMPARISON_PROMPT_VERSION,
    DISCOVERY_PROMPT_VERSION,
    GUIDANCE_PROMPT_VERSION,
)
from app.core.ai_cache import (
    get_cached_assistant_answer,
    set_cached_assistant_answer,
)
from app.schemas.assistant import (
    AssistantIntent,
    AssistantResponse,
)
from app.services.assistant_service import (
    _persist_interaction,
    detect_intent,
    stream_assistant,
)


def _prompt_version_for_intent(
    intent: AssistantIntent,
) -> str:
    if intent == AssistantIntent.COMPARISON:
        return COMPARISON_PROMPT_VERSION

    if intent == AssistantIntent.GUIDANCE:
        return GUIDANCE_PROMPT_VERSION

    return DISCOVERY_PROMPT_VERSION


async def stream_assistant_cached(
    db: Session,
    *,
    question: str,
    top_k: int = 5,
    llm: LLMProvider | None = None,
    correlation_id: str | None = None,
    user_id: uuid.UUID | None = None,
) -> AsyncIterator[
    dict[str, Any]
]:
    """
    Serve an identical completed assistant question from Redis
    when possible.

    Cache miss:
        normal RAG + LLM streaming

    Cache hit:
        no search
        no LLM call
        persist a new interaction
        replay the previously stored SSE events
    """

    started_at = time.perf_counter()

    cached = (
        get_cached_assistant_answer(
            question,
            top_k=top_k,
        )
    )

    # =========================================================
    # CACHE HIT
    # =========================================================

    if cached is not None:
        response = (
            AssistantResponse.model_validate(
                cached["response"]
            )
        )

        products = [
            {
                "product_id": (
                    citation.product_id
                ),
                "variant_id": (
                    citation.variant_id
                ),
            }
            for citation
            in response.citations
        ]

        # Every request must still appear in AI analytics,
        # even if Redis avoided another LLM call.
        _persist_interaction(
            db,
            question=question,
            response=response,
            products=products,
            started_at=started_at,
            input_tokens=0,
            output_tokens=0,
            status="completed",
            correlation_id=correlation_id,
            user_id=user_id,
        )

        for event in cached["events"]:
            yield event

        return

    # =========================================================
    # CACHE MISS
    # =========================================================

    events: list[
        dict[str, Any]
    ] = []

    async for event in stream_assistant(
        db,
        question=question,
        top_k=top_k,
        llm=llm,
        correlation_id=correlation_id,
        user_id=user_id,
    ):
        events.append(
            event
        )

        yield event

    if not events:
        return

    done_event = events[-1]

    # Only successful completed LLM answers are cached.
    # Refusals, failures and truncated streams are not cached.
    if (
        done_event.get("type")
        != "done"
        or done_event.get("status")
        != "completed"
    ):
        return

    intent = detect_intent(
        question
    )

    text = "".join(
        event.get(
            "text",
            "",
        )
        for event in events
        if event.get("type")
        == "text"
    )

    citations: list[dict] = []

    for event in events:
        if (
            event.get("type")
            == "citations"
        ):
            citations = event.get(
                "citations",
                [],
            )
            break

    response_payload = {
        "question": question,
        "answer": text,
        "intent": intent.value,
        "citations": citations,
        "refused": False,
        "prompt_version": (
            _prompt_version_for_intent(
                intent
            )
        ),
        "model": done_event.get(
            "model"
        ),
    }

    set_cached_assistant_answer(
        question,
        top_k=top_k,
        payload={
            "response": response_payload,
            "events": events,
        },
    )