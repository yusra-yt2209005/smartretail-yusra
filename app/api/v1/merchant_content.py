import json
import uuid

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
from app.core.dependencies import (
    require_role,
)
from app.db.session import get_db
from app.models.user import (
    User,
    UserRole,
)
from app.schemas.generated_content import (
    FAQGenerationRequest,
)
from app.services.content_generation_service import (
    get_owned_product,
    stream_description,
    stream_faq,
    stream_seo,
)
from app.core.ai_rate_limit import (
    enforce_ai_rate_limit,
)

router = APIRouter(
    prefix="/products",
    tags=["merchant-ai"],
)

def _encode_sse(
    event: dict,
) -> str:
    """
    Convert one merchant AI event into SSE wire format.
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
    "/{product_id}/generate/description",
)
async def generate_description(
    product_id: uuid.UUID,
    db: Session = Depends(
        get_db
    ),
    user: User = Depends(
        require_role(
            UserRole.MERCHANT,
            UserRole.ADMIN,
        )
    ),
) -> StreamingResponse:
    """
    Stream an AI-generated description for a product
    the current merchant is allowed to edit.
    """

    enforce_ai_rate_limit(
        user.id
    )

    product = get_owned_product(
        db,
        product_id=product_id,
        user=user,
    )

    correlation_id = (
        get_correlation_id()
    )

    async def event_generator():
        async for event in stream_description(
            product=product,
            db=db,
            user_id=user.id,
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


@router.post(
    "/{product_id}/generate/seo",
)
async def generate_seo(
    product_id: uuid.UUID,
    db: Session = Depends(
        get_db
    ),
    user: User = Depends(
        require_role(
            UserRole.MERCHANT,
            UserRole.ADMIN,
        )
    ),
) -> StreamingResponse:
    """
    Stream grounded SEO content for an owned product.
    """

    enforce_ai_rate_limit(
        user.id
    )

    product = get_owned_product(
        db,
        product_id=product_id,
        user=user,
    )

    correlation_id = (
        get_correlation_id()
    )

    async def event_generator():
        async for event in stream_seo(
            product=product,
            db=db,
            user_id=user.id,
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


@router.post(
    "/{product_id}/generate/faq",
)
async def generate_faq(
    product_id: uuid.UUID,
    data: FAQGenerationRequest,
    db: Session = Depends(
        get_db
    ),
    user: User = Depends(
        require_role(
            UserRole.MERCHANT,
            UserRole.ADMIN,
        )
    ),
) -> StreamingResponse:
    """
    Generate validated FAQ content for an owned product.
    """

    enforce_ai_rate_limit(
        user.id
    )

    product = get_owned_product(
        db,
        product_id=product_id,
        user=user,
    )

    correlation_id = (
        get_correlation_id()
    )

    async def event_generator():
        async for event in stream_faq(
            product=product,
            count=data.count,
            db=db,
            user_id=user.id,
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