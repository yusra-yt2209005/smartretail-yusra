from fastapi import (
    APIRouter,
    Depends,
)
from sqlalchemy.orm import Session

from app.services.assistant_service import (
    ask_discovery,
)

from app.db.session import get_db
from app.schemas.assistant import (
    AssistantRequest,
    AssistantResponse,
)
from app.services.assistant_service import (
    ask_assistant as ask_assistant_service,
)


router = APIRouter(
    prefix="/assistant",
    tags=["assistant"],
)


@router.post(
    "/ask",
    response_model=AssistantResponse,
)
async def ask_assistant(
    data: AssistantRequest,
    db: Session = Depends(
        get_db
    ),
) -> AssistantResponse:
    """
    Ask the SmartRetail shopping assistant.
    """

    return await ask_assistant_service(
        db,
        question=data.question,
        top_k=data.top_k,
    )