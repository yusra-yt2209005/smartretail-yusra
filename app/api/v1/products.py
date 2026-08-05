import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user_optional, require_role
from app.db.session import get_db
from app.models.product import ProductStatus
from app.models.user import User, UserRole
from app.schemas.common import Page
from app.schemas.product import (
    ProductCreate,
    ProductOut,
    ProductUpdate,
    VariantOut,
    VariantUpdate,
)
from app.services import product_service


router = APIRouter(
    prefix="/products",
    tags=["products"],
)


@router.get(
    "",
    response_model=Page[ProductOut],
)
def list_products(
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_current_user_optional),
    category_id: uuid.UUID | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    in_stock: bool | None = None,
    search: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    items, total = product_service.list_products(
        db,
        viewer=viewer,
        category_id=category_id,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        search=search,
        limit=limit,
        offset=offset,
    )

    return Page(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=ProductOut,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    data: ProductCreate,
    db: Session = Depends(get_db),
    merchant: User = Depends(
        require_role(UserRole.MERCHANT)
    ),
):
    return product_service.create_product(
        db,
        data,
        merchant,
    )


@router.get(
    "/{product_id}",
    response_model=ProductOut,
)
def get_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    return product_service.get_product(
        db,
        product_id,
    )


@router.patch(
    "/{product_id}",
    response_model=ProductOut,
)
def update_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_role(
            UserRole.MERCHANT,
            UserRole.ADMIN,
        )
    ),
):
    return product_service.update_product(
        db,
        product_id,
        data,
        user,
    )


@router.patch(
    "/{product_id}/variants/{variant_id}",
    response_model=VariantOut,
)
def update_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    data: VariantUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_role(
            UserRole.MERCHANT,
            UserRole.ADMIN,
        )
    ),
):
    return product_service.update_variant(
        db,
        product_id,
        variant_id,
        data,
        user,
    )


@router.post(
    "/{product_id}/publish",
    response_model=ProductOut,
)
def publish_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_role(
            UserRole.MERCHANT,
            UserRole.ADMIN,
        )
    ),
):
    return product_service.publish_product(
        db,
        product_id,
        user,
    )


@router.post(
    "/{product_id}/deactivate",
    response_model=ProductOut,
)
def deactivate_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_role(
            UserRole.MERCHANT,
            UserRole.ADMIN,
        )
    ),
):
    return product_service.set_product_status(
        db,
        product_id,
        ProductStatus.INACTIVE,
        user,
    )


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_role(
            UserRole.MERCHANT,
            UserRole.ADMIN,
        )
    ),
):
    product_service.delete_product(
        db,
        product_id,
        user,
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )

