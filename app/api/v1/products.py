import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session


from app.core.dependencies import get_current_user_optional, require_role
from app.db.session import get_db
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
from app.core.config import settings
from app.temporal.client import get_temporal_client
from app.temporal.workflows import ProductPublishingWorkflow

from app.core.cache import (
    get_cached_product_list,
    set_cached_product_list,
)


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
    viewer: User | None = Depends(
        get_current_user_optional
    ),
    category_id: uuid.UUID | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    in_stock: bool | None = None,
    search: str | None = None,
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
):
    cache_params = {
        "category_id": (
            str(category_id)
            if category_id is not None
            else None
        ),
        "min_price": (
            str(min_price)
            if min_price is not None
            else None
        ),
        "max_price": (
            str(max_price)
            if max_price is not None
            else None
        ),
        "in_stock": in_stock,
        "search": search,
        "limit": limit,
        "offset": offset,
    }

    if viewer is None:
        cached = get_cached_product_list(
            cache_params
        )

        if cached is not None:
            return cached

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

    page = Page[ProductOut](
        items=[
            ProductOut.model_validate(product)
            for product in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )

    if viewer is None:
        set_cached_product_list(
            cache_params,
            page.model_dump(
                mode="json"
            ),
        )

    return page


@router.post(
    "",
    response_model=ProductOut,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    data: ProductCreate,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_role(
            UserRole.MERCHANT,
            UserRole.ADMIN,
        )
    ),
):
    return product_service.create_product(
        db,
        data,
        user,
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
    status_code=status.HTTP_202_ACCEPTED,
)
async def publish_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_role(
            UserRole.MERCHANT,
            UserRole.ADMIN,
        )
    ),
):
    """
    Start the Temporal product publishing workflow.

    The API changes the product to PUBLISHING first, starts the
    workflow, then immediately returns 202 without waiting for the
    workflow to finish.
    """

    product_service.begin_product_publish(
        db,
        product_id,
        user,
    )

    client = await get_temporal_client()

    workflow_id = f"publish-product-{product_id}"

    try:
        handle = await client.start_workflow(
            ProductPublishingWorkflow.run,
            str(product_id),
            id=workflow_id,
            task_queue=settings.temporal_task_queue,
        )

    except Exception:
        product_service.mark_publish_start_failed(
            db,
            product_id,
        )
        raise

    return {
        "product_id": str(product_id),
        "workflow_id": handle.id,
        "status": "publishing",
    }

@router.get(
    "/{product_id}/publish-status",
)
async def publish_status(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_role(
            UserRole.MERCHANT,
            UserRole.ADMIN,
        )
    ),
):
    """
    Return both the product's durable database status and the
    Temporal workflow's current progress step.
    """

    product = (
        product_service.get_product_for_publish_status(
            db,
            product_id,
            user,
        )
    )

    client = await get_temporal_client()

    workflow_id = f"publish-product-{product_id}"

    handle = client.get_workflow_handle(
        workflow_id
    )

    try:
        step = await handle.query(
            ProductPublishingWorkflow.status
        )
    except Exception:
        step = None

    return {
        "product_id": str(product_id),
        "db_status": product.status.value,
        "workflow_step": step,
    }

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
    return product_service.deactivate_product(
        db,
        product_id,
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

