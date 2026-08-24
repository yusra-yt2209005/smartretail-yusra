import uuid

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import require_role
from app.core.idempotency import (
    get_stored_response,
    store_response,
)
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.order import OrderCreate, OrderOut
from app.services import order_service
from app.temporal.client import get_temporal_client
from app.temporal.workflows import (
    OrderSagaInput,
    OrderSagaWorkflow,
)


router = APIRouter(
    prefix="/orders",
    tags=["orders"],
)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_order(
    data: OrderCreate,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
    ),
    db: Session = Depends(get_db),
    customer: User = Depends(
        require_role(UserRole.CUSTOMER)
    ),
):
    """
    Create a PLACED order and start its Temporal saga.

    Returns 202 immediately without waiting for the saga to finish.
    """

    # ---------------------------------------------------------
    # 1. Check Redis for a previous response using this key.
    # ---------------------------------------------------------
    stored = get_stored_response(
        customer.id,
        idempotency_key,
    )

    if stored is not None:
        return stored["body"]

    # ---------------------------------------------------------
    # 2. Create the initial Order + OrderItems.
    # ---------------------------------------------------------
    order = order_service.build_order(
        db,
        customer,
        data,
        idempotency_key,
    )

    # ---------------------------------------------------------
    # 3. Start the Temporal OrderSagaWorkflow.
    # ---------------------------------------------------------
    temporal_client = await get_temporal_client()

    workflow_id = f"order-saga-{order.id}"

    await temporal_client.start_workflow(
        OrderSagaWorkflow.run,
        OrderSagaInput(
            order_id=str(order.id),
            idempotency_key=idempotency_key,
        ),
        id=workflow_id,
        task_queue=settings.temporal_task_queue,
    )

    # ---------------------------------------------------------
    # 4. Build the immediate 202 response.
    # ---------------------------------------------------------
    body = {
        "order_id": str(order.id),
        "workflow_id": workflow_id,
        "status": order.status.value,
    }

    # ---------------------------------------------------------
    # 5. Remember this response in Redis for duplicate requests.
    # ---------------------------------------------------------
    store_response(
        customer.id,
        idempotency_key,
        status.HTTP_202_ACCEPTED,
        body,
    )

    return body


@router.get(
    "/{order_id}",
    response_model=OrderOut,
)
def get_order(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    customer: User = Depends(
        require_role(UserRole.CUSTOMER)
    ),
):
    """
    Return the current persisted state of the customer's order.
    """

    return order_service.get_order(
        db,
        order_id,
        customer,
    )