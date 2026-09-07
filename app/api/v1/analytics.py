from datetime import date

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from sqlalchemy.orm import Session

from app.core.dependencies import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.analytics import (
    AnalyticsReconciliationOut,
    AnalyticsSummaryOut,
)
from app.services import analytics_service


router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
)


@router.get(
    "/summary",
    response_model=AnalyticsSummaryOut,
)
def get_analytics_summary(
    start_date: date | None = None,
    end_date: date | None = None,
    top_n: int = Query(
        default=10,
        ge=1,
        le=100,
    ),
    db: Session = Depends(get_db),
    _admin: User = Depends(
        require_role(
            UserRole.ADMIN
        )
    ),
):
    if (
        start_date is not None
        and end_date is not None
        and start_date > end_date
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "start_date cannot be "
                "after end_date"
            ),
        )

    return analytics_service.get_summary(
        db,
        start_date=start_date,
        end_date=end_date,
        top_n=top_n,
    )


@router.get(
    "/reconcile",
    response_model=AnalyticsReconciliationOut,
)
def reconcile_analytics(
    day: date,
    db: Session = Depends(get_db),
    _admin: User = Depends(
        require_role(
            UserRole.ADMIN
        )
    ),
):
    return analytics_service.reconcile_day(
        db,
        day,
    )