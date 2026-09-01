from fastapi import (
    APIRouter,
    Depends,
)
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.search import (
    SearchRequest,
    SearchResponse,
)
from app.services.search_service import (
    search_products,
)


router = APIRouter(
    tags=["search"]
)


@router.post(
    "/search",
    response_model=SearchResponse,
)
def semantic_search(
    data: SearchRequest,
    db: Session = Depends(
        get_db
    ),
) -> SearchResponse:
    """
    Semantic search over the buyable product catalog.
    """

    items = search_products(
        db,
        query=data.query,
        top_k=data.top_k,
    )

    message = None

    if not items:
        message = (
            "No matching products found."
        )

    return SearchResponse(
        query=data.query,
        items=items,
        message=message,
    )