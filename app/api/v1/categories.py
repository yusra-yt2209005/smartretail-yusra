import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate
from app.services import category_service


# GET    /categories
# GET    /categories/{category_id}
# POST   /categories
# PATCH  /categories/{category_id}
# DELETE /categories/{category_id}

router = APIRouter(
    prefix="/categories",
    tags=["categories"],
)


@router.get(
    "",
    response_model=list[CategoryOut],
)
def list_categories(
    db: Session = Depends(get_db),
):
    """
    Public endpoint: anyone can browse categories.
    """
    return category_service.list_categories(db)


@router.get(
    "/{category_id}",
    response_model=CategoryOut,
)
def get_category(
    category_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """
    Return one category by UUID.
    """
    return category_service.get_category(
        db,
        category_id,
    )


@router.post(
    "",
    response_model=CategoryOut,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    data: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            UserRole.MERCHANT,
            UserRole.ADMIN,
        )
    ),
):
    """
    Merchants and admins may create categories.
    """
    return category_service.create_category(
        db,
        data,
    )


@router.patch(
    "/{category_id}",
    response_model=CategoryOut,
)
def update_category(
    category_id: uuid.UUID,
    data: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(
            UserRole.MERCHANT,
            UserRole.ADMIN,
        )
    ),
):
    """
    Merchants and admins may update categories.
    """
    return category_service.update_category(
        db,
        category_id,
        data,
    )


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_category(
    category_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role(UserRole.ADMIN)
    ),
):
    """
    Only admins may delete categories.
    """
    category_service.delete_category(
        db,
        category_id,
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )