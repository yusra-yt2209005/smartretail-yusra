import json

from fastapi import (
    APIRouter,
    Depends,
)
from fastapi.responses import (
    StreamingResponse,
)
from sqlalchemy.orm import Session

from app.core.correlation import (
    get_correlation_id,
)
from app.db.session import get_db
from app.schemas.assistant import (
    AssistantRequest,
)
from app.services.assistant_service import (
    stream_assistant,
)


router = APIRouter(
    prefix="/assistant",
    tags=["assistant"],
)


def _encode_sse(
    event: dict,
) -> str:
    """
    Convert one application event into SSE wire format.
    """

    event_type = event["type"]

    payload = {
        key: value
        for key, value in event.items()
        if key != "type"
    }

    return (
        f"event: {event_type}\n"
        f"data: {json.dumps(payload)}\n\n"
    )


@router.post(
    "/ask",
)
async def ask_assistant(
    data: AssistantRequest,
    db: Session = Depends(
        get_db
    ),
) -> StreamingResponse:
    """
    Stream a grounded SmartRetail shopping-assistant response
    using Server-Sent Events.
    """

    # Capture this while the normal request correlation context
    # is definitely still active.
    correlation_id = (
        get_correlation_id()
    )

    async def event_generator():
        async for event in stream_assistant(
            db,
            question=data.question,
            top_k=data.top_k,
            correlation_id=correlation_id,
        ):
            yield _encode_sse(
                event
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )