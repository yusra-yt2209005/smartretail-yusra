import hashlib
import json
import uuid
import time
from datetime import UTC, datetime
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.db.session import SessionLocal
from app.models.content_chunk import ContentChunk
from app.models.product import Product, ProductStatus

from app.models.inventory_reservation import (
    InventoryReservation,
    ReservationStatus,
)
from app.models.order import (
    Order,
    OrderStatus,
)
from app.models.order_item import OrderItem
from app.models.order_status_history import (
    OrderStatusHistory,
)
from app.models.payment import (
    Payment,
    PaymentStatus,
)
from app.models.shipment import (
    Shipment,
    ShipmentStatus,
)
from app.services import inventory_service
from app.services.payment_service import (
    PaymentAuthorizer,
)

from app.core.cache import (
    bump_product_list_cache_version,
)

from app.workers.tasks.notifications import send_order_notification


from app.events.outbox import enqueue
from app.models.product_variant import ProductVariant

#ORDER ACTIVTY
# reserve_inventory_activity
# release_inventory_activity

# authorize_payment_activity
# refund_payment_activity

# create_shipment_activity
# notify_customer_activity
# confirm_order_activity

# reject/cancel/fail order activity


# -------------------------------------------------------------------------
# Temporal Activity input objects
# -------------------------------------------------------------------------


@dataclass
class ProductIdInput:
    """
    Input for Activities that only need a product ID.
    """

    product_id: str


@dataclass
class ChunkProductInput:
    """
    Input for the chunking Activity.

    The catalog-building Activity creates the text first, then the
    Workflow passes that text into the chunking Activity.
    """

    product_id: str
    catalog_text: str


@dataclass
class MarkFailedInput:
    """
    Input used when the publishing Workflow fails.
    """

    product_id: str
    reason: str

#---------Order Dataclass
@dataclass
class OrderIdInput:
    order_id: str


@dataclass
class AuthorizePaymentInput:
    order_id: str
    idempotency_key: str


@dataclass
class PaymentIdInput:
    payment_id: str


@dataclass
class FailOrderInput:
    order_id: str
    reason: str


# -------------------------------------------------------------------------
# Product publishing Activities
# -------------------------------------------------------------------------


@activity.defn
def validate_product_activity(
    input: ProductIdInput,
) -> dict:
    """
    Validate that a product is ready to be published.

    This contains the same publishing validation rules that Week 1
    performed synchronously.

    Idempotency:
    This Activity only reads from the database, so running it multiple
    times does not change database state.
    """

    product_id = uuid.UUID(input.product_id)

    with SessionLocal() as db:
        product = db.scalar(
            select(Product)
            .options(
                selectinload(Product.variants),
            )
            .where(Product.id == product_id)
        )

        if product is None:
            raise ApplicationError(
                f"Product '{product_id}' was not found",
                type="ProductNotFound",
                non_retryable=True,
            )

        errors: list[str] = []

        if not product.title.strip():
            errors.append(
                "title is required" #title exists
            )

        if not product.description.strip():
            errors.append(
                "description is required"  # description exists
            )

        if not product.variants:
            errors.append(
                "at least one variant is required"  # at least 1 variant exists
            )

        for variant in product.variants:
            if variant.price <= 0:
                errors.append(
                    f"variant '{variant.sku}' must have "  #Valid price
                    f"a price greater than 0"
                )

            if variant.stock < 0:
                errors.append(
                    f"variant '{variant.sku}' cannot "  #valid stock qty
                    f"have negative stock"
                )

        if errors:
            raise ApplicationError(
                "; ".join(errors),
                type="ProductValidationError",
                non_retryable=True,
            )

        return {
            "valid": True,
        }


@activity.defn
def process_media_activity(
    input: ProductIdInput,
) -> dict:
    """
    Simulate processing all media belonging to the product.

    Week 2 does not perform real image processing. Instead, each media
    row is marked processed=True.

    Idempotency:
    Setting processed=True again has the same final result, so Temporal
    can safely retry this Activity.
    """

    product_id = uuid.UUID(input.product_id)

    with SessionLocal() as db:
        product = db.scalar(
            select(Product)
            .options(
                selectinload(Product.media),
            )
            .where(Product.id == product_id)
        )

        if product is None:
            raise ApplicationError(
                f"Product '{product_id}' was not found",
                type="ProductNotFound",
                non_retryable=True,
            )

        for media in product.media:
            media.processed = True    #simulated processing

        db.commit()

        return {
            "media_processed": len(product.media),
        }


@activity.defn
def build_catalog_activity(
    input: ProductIdInput,
) -> str:
    """
    Build an enriched catalog representation of the product.

    The result combines:
    - product title
    - category
    - description
    - variant SKUs
    - prices
    - variant attributes

    The returned text is passed to chunk_product_activity.

    Idempotency:
    This Activity only reads database state and returns derived text.
    """

    product_id = uuid.UUID(input.product_id)

    with SessionLocal() as db:
        product = db.scalar(
            select(Product)
            .options(
                selectinload(Product.variants),
                selectinload(Product.category),
            )
            .where(Product.id == product_id)
        )

        if product is None:
            raise ApplicationError(
                f"Product '{product_id}' was not found",
                type="ProductNotFound",
                non_retryable=True,
            )

        category_name = (
            product.category.name
            if product.category is not None
            else "Uncategorized"
        )

        variant_parts: list[str] = []

        # Sort by SKU so the generated text is stable.
        for variant in sorted(
            product.variants,
            key=lambda item: item.sku,
        ):
            attributes = json.dumps(
                variant.attributes or {},
                sort_keys=True,
            )

            variant_parts.append(
                (
                    f"SKU: {variant.sku}; "
                    f"Price: {variant.price}; "
                    f"Attributes: {attributes}"
                )
            )

        variants_text = " | ".join(
            variant_parts
        )

        catalog_text = (
            f"Title: {product.title.strip()}\n"
            f"Category: {category_name}\n"
            f"Description: {product.description.strip()}\n"
            f"Variants: {variants_text}"
        )

        return catalog_text


@activity.defn
def chunk_product_activity(
    input: ChunkProductInput,
) -> dict:
    """
    Store the current searchable product text as a ContentChunk.

    Week 2 creates one enriched chunk per product.

    Idempotency:
    Existing chunks for this product are deleted before the new chunk
    is inserted. Therefore retries or future re-publishing replace the
    old data instead of creating duplicate/stale chunks.
    """

    product_id = uuid.UUID(input.product_id)
    catalog_text = input.catalog_text.strip()

    if not catalog_text:
        raise ApplicationError(
            "Catalog text cannot be empty",
            type="EmptyCatalogText",
            non_retryable=True,
        )

    text_hash = hashlib.sha256(
        catalog_text.encode("utf-8")
    ).hexdigest()

    with SessionLocal() as db:
        product = db.get(
            Product,
            product_id,
        )

        if product is None:
            raise ApplicationError(
                f"Product '{product_id}' was not found",
                type="ProductNotFound",
                non_retryable=True,
            )

        # Remove any previous chunks for this product.
        #
        # Delete + insert happens in the same transaction because commit()
        # happens only after the new chunk has been added.
        db.execute(
            delete(ContentChunk).where(
                ContentChunk.product_id == product_id
            )
        )

        chunk = ContentChunk(
            product_id=product_id,
            chunk_index=0,
            text=catalog_text,
            text_hash=text_hash,
            embedded_at=None,
        )

        db.add(chunk)
        db.commit()

        return {
            "chunks_written": 1,
            "text_hash": text_hash,
        }


@activity.defn
def mark_product_published_activity(
    input: ProductIdInput,
) -> dict:
    """
    Final successful publishing step.

    The product only becomes PUBLISHED after all previous publishing
    Activities have succeeded.

    Idempotency:
    If this Activity is retried after already succeeding, PUBLISHED
    remains PUBLISHED.
    """

    product_id = uuid.UUID(input.product_id)

    with SessionLocal() as db:
        product = db.get(
            Product,
            product_id,
        )

        if product is None:
            raise ApplicationError(
                f"Product '{product_id}' was not found",
                type="ProductNotFound",
                non_retryable=True,
            )

        # A retry after successful completion is harmless.
        if product.status == ProductStatus.PUBLISHED:
            return {
                "status": ProductStatus.PUBLISHED.value,
            }

        # Normally the endpoint will put the product into PUBLISHING
        # before starting this Workflow.
        if product.status != ProductStatus.PUBLISHING:
            raise ApplicationError(
                (
                    "Cannot mark product as published while "
                    f"status is '{product.status.value}'"
                ),
                type="InvalidProductState",
                non_retryable=True,
            )


        product.status = ProductStatus.PUBLISHED
        if product.published_at is None:
            product.published_at = datetime.now(UTC)

        enqueue(
            db,
            event_type="product.published",
            data={
                "product_id": str(product.id),
                "published_at": product.published_at.isoformat(),
            },
            correlation_id=f"product-{product.id}",
        )

        db.commit()
        bump_product_list_cache_version()
        return {
            "status": ProductStatus.PUBLISHED.value,
        }


@activity.defn
def mark_product_publish_failed_activity(
    input: MarkFailedInput,
) -> dict:
    """
    Record a failed publishing Workflow.

    This prevents products from remaining stuck in PUBLISHING after a
    permanent workflow failure.

    Idempotency:
    Repeated calls leave the product in the same PUBLISH_FAILED state.

    A successfully PUBLISHED product is never changed back to
    PUBLISH_FAILED.
    """

    product_id = uuid.UUID(input.product_id)

    with SessionLocal() as db:
        product = db.get(
            Product,
            product_id,
        )

        # If the product itself disappeared, there is nothing left to
        # update. Avoid masking the original workflow failure.
        if product is None:
            return {
                "status": "not_found",
                "reason": input.reason,
            }

        # Never undo successful publication.
        if product.status == ProductStatus.PUBLISHED:
            return {
                "status": ProductStatus.PUBLISHED.value,
                "reason": input.reason,
            }

        product.status = ProductStatus.PUBLISH_FAILED

        db.commit()
        bump_product_list_cache_version()
        return {
            "status": ProductStatus.PUBLISH_FAILED.value,
            "reason": input.reason,
        }

#-----------------------------------------------------------------------------
#-------------------ORDER ACTIVITIES------------------------------------------

def _record_order_transition(
    db,
    order: Order,
    to_status: OrderStatus,
    reason: str | None = None,
) -> None:
    """
    Change the current order status and preserve the transition in
    order_status_history.

    If the order is already in the requested state, do nothing.
    This helps make retried Activities idempotent.
    """

    if order.status == to_status:
        return

    from_status = order.status

    order.status = to_status

    db.add(
        OrderStatusHistory(
            order_id=order.id,
            from_status=from_status,
            to_status=to_status,
            actor="workflow",
            reason=reason,
        )
    )

@activity.defn
def reserve_inventory_activity(
    input: OrderIdInput,
) -> dict:
    """
    Reserve every variant requested by an order.

    Each stock decrement, InventoryReservation row, and
    inventory.reserved outbox event are committed together.

    This keeps the reservation retry-safe and guarantees that
    an event is recorded only when the reservation succeeds.
    """

    order_id = uuid.UUID(
        input.order_id
    )

    with SessionLocal() as db:
        order = db.get(
            Order,
            order_id,
        )

        if order is None:
            raise ApplicationError(
                f"Order '{order_id}' was not found",
                type="OrderNotFound",
                non_retryable=True,
            )

        items = db.scalars(
            select(OrderItem).where(
                OrderItem.order_id == order_id
            )
        ).all()

        # Combine duplicate variants if the same variant
        # somehow appears more than once in an order.
        quantities: dict[uuid.UUID, int] = {}

        for item in items:
            quantities[item.variant_id] = (
                quantities.get(
                    item.variant_id,
                    0,
                )
                + item.qty
            )

        reserved_count = 0

        for variant_id, qty in quantities.items():

            existing = db.scalar(
                select(
                    InventoryReservation
                ).where(
                    InventoryReservation.order_id
                    == order_id,
                    InventoryReservation.variant_id
                    == variant_id,
                )
            )

            if existing is not None:
                if (
                    existing.status
                    == ReservationStatus.RESERVED
                ):
                    reserved_count += 1
                    continue

                if (
                    existing.status
                    == ReservationStatus.COMMITTED
                ):
                    reserved_count += 1
                    continue

                raise ApplicationError(
                    (
                        "Inventory reservation was already "
                        "released for variant "
                        f"'{variant_id}'"
                    ),
                    type="ReservationAlreadyReleased",
                    non_retryable=True,
                )

            reserved = (
                inventory_service.try_reserve_stock(
                    db,
                    variant_id,
                    qty,
                    commit=False,
                )
            )

            if not reserved:
                raise ApplicationError(
                    (
                        "Insufficient stock for variant "
                        f"'{variant_id}'"
                    ),
                    type="InsufficientStock",
                    non_retryable=True,
                )

            db.add(
                InventoryReservation(
                    order_id=order_id,
                    variant_id=variant_id,
                    qty=qty,
                    status=(
                        ReservationStatus.RESERVED
                    ),
                )
            )

            # Read the stock AFTER the successful atomic decrement.
            remaining_stock = db.scalar(
                select(
                    ProductVariant.stock
                ).where(
                    ProductVariant.id == variant_id
                )
            )

            reserved_at = datetime.now(UTC)

            # The event is inserted into the SAME transaction as
            # the stock decrement and reservation row.
            enqueue(
                db,
                event_type="inventory.reserved",
                data={
                    "order_id": input.order_id,
                    "variant_id": str(
                        variant_id
                    ),
                    "qty": qty,
                    "stockout": (
                        remaining_stock == 0
                    ),
                    "reserved_at": (
                        reserved_at.isoformat()
                    ),
                },
                correlation_id=(
                    f"order-{input.order_id}"
                ),
            )

            # These three things become durable together:
            # 1. stock decrement
            # 2. reservation row
            # 3. inventory.reserved outbox event
            db.commit()

            reserved_count += 1

        _record_order_transition(
            db,
            order,
            OrderStatus.RESERVED,
        )

        db.commit()

        bump_product_list_cache_version()

        return {
            "reserved_items": reserved_count
        }

@activity.defn
def release_inventory_activity(
    input: OrderIdInput,
) -> dict:
    """
    Compensation for inventory reservation.

    Only RESERVED rows are released, so running this Activity twice
    cannot add the same stock back twice.
    """

    order_id = uuid.UUID(
        input.order_id
    )

    released_count = 0

    with SessionLocal() as db:
        reservations = db.scalars(
            select(
                InventoryReservation
            ).where(
                InventoryReservation.order_id
                == order_id,
                InventoryReservation.status
                == ReservationStatus.RESERVED,
            )
        ).all()

        for reservation in reservations:

            inventory_service.release_stock(
                db,
                reservation.variant_id,
                reservation.qty,
                commit=False,
            )

            reservation.status = (
                ReservationStatus.RELEASED
            )

            # Stock restoration + RELEASED state commit together.
            db.commit()

            released_count += 1


    if released_count > 0:
        bump_product_list_cache_version()
    return {
        "released": released_count
    }

@activity.defn
def authorize_payment_activity(
    input: AuthorizePaymentInput,
) -> dict:
    """
    Simulate payment authorization.

    An existing payment for this order + idempotency key is reused,
    making Temporal retries safe.
    """

    order_id = uuid.UUID(
        input.order_id
    )

    with SessionLocal() as db:
        order = db.get(
            Order,
            order_id,
        )

        if order is None:
            raise ApplicationError(
                f"Order '{order_id}' was not found",
                type="OrderNotFound",
                non_retryable=True,
            )

        existing = db.scalar(
            select(Payment).where(
                Payment.order_id == order_id,
                Payment.idempotency_key
                == input.idempotency_key,
            )
        )

        if existing is not None:

            if (
                existing.status
                == PaymentStatus.FAILED
            ):
                raise ApplicationError(
                    "Payment previously declined",
                    type="PaymentDeclined",
                    non_retryable=True,
                )

            if (
                existing.status
                == PaymentStatus.REFUNDED
            ):
                raise ApplicationError(
                    "Payment was already refunded",
                    type="PaymentAlreadyRefunded",
                    non_retryable=True,
                )

            _record_order_transition(
                db,
                order,
                OrderStatus.PAID,
            )

            db.commit()

            return {
                "payment_id": str(existing.id),
                "status": (
                    PaymentStatus.AUTHORIZED.value
                ),
            }

        result = PaymentAuthorizer().authorize(
            total=order.total,
            idempotency_key=(
                input.idempotency_key
            ),
        )

        payment = Payment(
            order_id=order_id,
            amount=order.total,
            status=(
                PaymentStatus.AUTHORIZED
                if result.success
                else PaymentStatus.FAILED
            ),
            provider_ref=result.provider_ref,
            idempotency_key=(
                input.idempotency_key
            ),
        )

        db.add(payment)
        db.commit()
        db.refresh(payment)

        if not result.success:
            raise ApplicationError(
                (
                    "Payment declined: "
                    f"{result.reason}"
                ),
                type="PaymentDeclined",
                non_retryable=True,
            )

        _record_order_transition(
            db,
            order,
            OrderStatus.PAID,
        )
        enqueue(
            db,
            event_type="payment.succeeded",
            data={
                "order_id": input.order_id,
                "payment_id": str(payment.id),
                "amount": str(payment.amount),
            },
            correlation_id=f"order-{input.order_id}",
        )
        db.commit()

        return {
            "payment_id": str(payment.id),
            "status": (
                PaymentStatus.AUTHORIZED.value
            ),
        }

@activity.defn
def refund_payment_activity(
    input: PaymentIdInput,
) -> dict:
    """
    Compensation for a successfully authorized payment.

    In Week 2 the refund is simulated by changing the Payment status.
    """

    payment_id = uuid.UUID(
        input.payment_id
    )

    with SessionLocal() as db:
        payment = db.get(
            Payment,
            payment_id,
        )

        if payment is None:
            raise ApplicationError(
                f"Payment '{payment_id}' was not found",
                type="PaymentNotFound",
                non_retryable=True,
            )

        # Retry-safe: already refunded means the compensation
        # has already happened.
        if (
            payment.status
            == PaymentStatus.REFUNDED
        ):
            return {
                "payment_id": str(payment.id),
                "status": (
                    PaymentStatus.REFUNDED.value
                ),
            }

        if (
            payment.status
            != PaymentStatus.AUTHORIZED
        ):
            raise ApplicationError(
                (
                    "Only an authorized payment "
                    "can be refunded"
                ),
                type="InvalidPaymentState",
                non_retryable=True,
            )

        payment.status = PaymentStatus.REFUNDED

        order = db.get(
            Order,
            payment.order_id,
        )

        if order is not None:
            _record_order_transition(
                db,
                order,
                OrderStatus.REFUNDED,
                reason=(
                    "Saga compensation refunded "
                    "authorized payment"
                ),
            )

        db.commit()

        return {
            "payment_id": str(payment.id),
            "status": (
                PaymentStatus.REFUNDED.value
            ),
        }

@activity.defn
def create_shipment_activity(
    input: OrderIdInput,
) -> dict:
    """
    Create one simulated shipment for the order.

    If the Activity is retried, reuse the existing shipment.
    """

    order_id = uuid.UUID(
        input.order_id
    )

    with SessionLocal() as db:
        order = db.get(
            Order,
            order_id,
        )

        if order is None:
            raise ApplicationError(
                f"Order '{order_id}' was not found",
                type="OrderNotFound",
                non_retryable=True,
            )

        shipment = db.scalar(
            select(Shipment).where(
                Shipment.order_id == order_id
            )
        )

        if shipment is None:
            shipment = Shipment(
                order_id=order_id,
                status=ShipmentStatus.DISPATCHED,
                address={},
            )

            db.add(shipment)
            db.flush()

        elif (
            shipment.status
            == ShipmentStatus.CREATED
        ):
            shipment.status = (
                ShipmentStatus.DISPATCHED
            )

        _record_order_transition(
            db,
            order,
            OrderStatus.SHIPPED,
        )
        enqueue(
            db,
            event_type="shipment.created",
            data={
                "order_id": input.order_id,
                "shipment_id": str(shipment.id),
            },
            correlation_id=f"order-{input.order_id}",
        )
        db.commit()
        db.refresh(shipment)

        return {
            "shipment_id": str(shipment.id)
        }

@activity.defn
def notify_customer_activity(
    input: OrderIdInput,
) -> dict:
    send_order_notification.delay(
        input.order_id,
        "completed",
    )

    return {
        "queued": True,
        "order_id": input.order_id,
    }


@activity.defn
def confirm_order_activity(
    input: OrderIdInput,
) -> dict:
    """
    Simulate successful delivery and finish the order.

    Records:
        SHIPPED -> DELIVERED -> COMPLETED

    Reserved inventory becomes COMMITTED because the order has now
    successfully consumed it.
    """

    order_id = uuid.UUID(
        input.order_id
    )

    with SessionLocal() as db:
        order = db.get(
            Order,
            order_id,
        )

        if order is None:
            raise ApplicationError(
                f"Order '{order_id}' was not found",
                type="OrderNotFound",
                non_retryable=True,
            )

        if (
            order.status
            == OrderStatus.COMPLETED
        ):
            return {
                "status": (
                    OrderStatus.COMPLETED.value
                )
            }

        shipment = db.scalar(
            select(Shipment).where(
                Shipment.order_id == order_id
            )
        )

        if shipment is not None:
            shipment.status = (
                ShipmentStatus.DELIVERED
            )

        if (
            order.status
            != OrderStatus.DELIVERED
        ):
            _record_order_transition(
                db,
                order,
                OrderStatus.DELIVERED,
            )

        _record_order_transition(
            db,
            order,
            OrderStatus.COMPLETED,
        )
        enqueue(
            db,
            event_type="order.confirmed",
            data={
                "order_id": input.order_id,
                "customer_id": str(order.customer_id),
                "total": str(order.total),
            },
            correlation_id=f"order-{input.order_id}",
        )

        reservations = db.scalars(
            select(
                InventoryReservation
            ).where(
                InventoryReservation.order_id
                == order_id,
                InventoryReservation.status
                == ReservationStatus.RESERVED,
            )
        ).all()

        for reservation in reservations:
            reservation.status = (
                ReservationStatus.COMMITTED
            )

        db.commit()

        return {
            "status": (
                OrderStatus.COMPLETED.value
            )
        }

#-----Add rejection and cancellation Activities
@activity.defn
def reject_order_activity(
    input: FailOrderInput,
) -> dict:
    """
    Mark an order REJECTED when it cannot proceed because inventory
    could not be reserved.
    """

    order_id = uuid.UUID(
        input.order_id
    )

    with SessionLocal() as db:
        order = db.get(
            Order,
            order_id,
        )

        if order is None:
            raise ApplicationError(
                f"Order '{order_id}' was not found",
                type="OrderNotFound",
                non_retryable=True,
            )

        _record_order_transition(
            db,
            order,
            OrderStatus.REJECTED,
            reason=input.reason,
        )

        db.commit()

        return {
            "status": (
                OrderStatus.REJECTED.value
            ),
            "reason": input.reason,
        }

@activity.defn
def cancel_order_activity(
    input: FailOrderInput,
) -> dict:
    """
    Mark an order CANCELLED after required compensation has completed.
    """

    order_id = uuid.UUID(
        input.order_id
    )

    with SessionLocal() as db:
        order = db.get(
            Order,
            order_id,
        )

        if order is None:
            raise ApplicationError(
                f"Order '{order_id}' was not found",
                type="OrderNotFound",
                non_retryable=True,
            )

        _record_order_transition(
            db,
            order,
            OrderStatus.CANCELLED,
            reason=input.reason,
        )

        db.commit()

        return {
            "status": (
                OrderStatus.CANCELLED.value
            ),
            "reason": input.reason,
        }
