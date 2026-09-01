from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities import (
        AuthorizePaymentInput,
        ChunkProductInput,
        FailOrderInput,
        MarkFailedInput,
        OrderIdInput,
        PaymentIdInput,
        ProductIdInput,
        authorize_payment_activity,
        build_catalog_activity,
        cancel_order_activity,
        chunk_product_activity,
        embed_product_chunks_activity,
        confirm_order_activity,
        create_shipment_activity,
        mark_product_publish_failed_activity,
        mark_product_published_activity,
        notify_customer_activity,
        process_media_activity,
        refund_payment_activity,
        reject_order_activity,
        release_inventory_activity,
        reserve_inventory_activity,
        validate_product_activity,
    )



DEFAULT_TIMEOUT = timedelta(seconds=30)

DEFAULT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=3,
)

@dataclass
class OrderSagaInput:
    order_id: str
    idempotency_key: str
    correlation_id: str

@workflow.defn
class HelloWorkflow:
    """
    Simple workflow used in 2.2 to verify Temporal end-to-end.
    """

    @workflow.run
    async def run(self, name: str) -> str:
        return f"Hello, {name}!"


@workflow.defn
class ProductPublishingWorkflow:
    """
    Durable product publishing pipeline.

    validate
        -> process media
        -> build catalog
        -> chunk
        -> mark PUBLISHED

    The Workflow only controls execution order.
    Database I/O is performed inside Activities.
    """

    def __init__(self) -> None:
        self._step = "queued"

    @workflow.query
    def status(self) -> str:
        """
        Return the current publishing step.

        This can later support a publish-status API endpoint.
        """
        return self._step

    @workflow.run
    async def run(
        self,
        product_id: str,
    ) -> dict:
        try:
            # ---------------------------------------------------------
            # 1. Validate
            # ---------------------------------------------------------
            self._step = "validating"

            await workflow.execute_activity(
                validate_product_activity,
                ProductIdInput(
                    product_id=product_id,
                ),
                start_to_close_timeout=DEFAULT_TIMEOUT,
                retry_policy=DEFAULT_RETRY,
            )

            # ---------------------------------------------------------
            # 2. Process media
            # ---------------------------------------------------------
            self._step = "processing_media"

            await workflow.execute_activity(
                process_media_activity,
                ProductIdInput(
                    product_id=product_id,
                ),
                start_to_close_timeout=DEFAULT_TIMEOUT,
                retry_policy=DEFAULT_RETRY,
            )

            # ---------------------------------------------------------
            # 3. Build catalog representation
            # ---------------------------------------------------------
            self._step = "building_catalog"

            catalog_text = await workflow.execute_activity(
                build_catalog_activity,
                ProductIdInput(
                    product_id=product_id,
                ),
                start_to_close_timeout=DEFAULT_TIMEOUT,
                retry_policy=DEFAULT_RETRY,
            )

            # ---------------------------------------------------------
            # 4. Create/replace content chunks
            # ---------------------------------------------------------
            self._step = "chunking"

            chunk_result = await workflow.execute_activity(
                chunk_product_activity,
                ChunkProductInput(
                    product_id=product_id,
                    catalog_text=catalog_text,
                ),
                start_to_close_timeout=timedelta(
                    seconds=60
                ),
                retry_policy=DEFAULT_RETRY,
            )
            # ---------------------------------------------------------
            # 5. Generate and store embeddings
            # ---------------------------------------------------------
            self._step = "embedding"

            embedding_result = await workflow.execute_activity(
                embed_product_chunks_activity,
                ProductIdInput(
                    product_id=product_id,
                ),
                start_to_close_timeout=timedelta(
                    seconds=60
                ),
                retry_policy=DEFAULT_RETRY,
            )
            # ---------------------------------------------------------
            # 6. Mark publishing successful
            # ---------------------------------------------------------
            self._step = "publishing"

            await workflow.execute_activity(
                mark_product_published_activity,
                ProductIdInput(
                    product_id=product_id,
                ),
                start_to_close_timeout=DEFAULT_TIMEOUT,
                retry_policy=DEFAULT_RETRY,
            )

            self._step = "published"

            return {
                "product_id": product_id,
                "status": "published",
                **chunk_result,
                **embedding_result,
            }

        except Exception as exc:
            self._step = "publish_failed"

            # Record the permanent publishing failure so the product
            # does not remain stuck in PUBLISHING.
            await workflow.execute_activity(
                mark_product_publish_failed_activity,
                MarkFailedInput(
                    product_id=product_id,
                    reason=str(exc),
                ),
                start_to_close_timeout=DEFAULT_TIMEOUT,
                retry_policy=DEFAULT_RETRY,
            )

            # Re-raise so Temporal still records the Workflow itself
            # as failed rather than pretending it succeeded.
            raise


@workflow.defn
class OrderSagaWorkflow:
    """
    Durable order-processing saga.

    Forward path:
        reserve inventory
        -> authorize payment
        -> create shipment
        -> notify customer
        -> confirm order

    Compensation:
        - reservation failure:
            release any partial reservation -> REJECTED

        - payment failure:
            release inventory -> CANCELLED

        - failure after payment:
            CANCELLED -> refund payment -> release inventory
            -> REFUNDED
    """

    def __init__(self) -> None:
        self._step = "queued"

    @workflow.query
    def status(self) -> str:
        """
        Return the current saga step.

        This can later be exposed by GET /orders/{id}.
        """
        return self._step

    @workflow.run
    async def run(
        self,
        input: OrderSagaInput,
    ) -> dict:

        order_id = input.order_id

        # ============================================================
        # 1. RESERVE INVENTORY
        # ============================================================

        self._step = "reserving_inventory"

        try:
            await workflow.execute_activity(
                reserve_inventory_activity,
                OrderIdInput(
                    order_id=order_id,
                    correlation_id=input.correlation_id,
                ),
                start_to_close_timeout=DEFAULT_TIMEOUT,
                retry_policy=DEFAULT_RETRY,
            )

        except Exception as exc:
            # reserve_inventory_activity may have reserved some items
            # before another item ran out of stock.
            #
            # Release anything that was successfully reserved first.
            self._step = "releasing_partial_inventory"

            await workflow.execute_activity(
                release_inventory_activity,
                OrderIdInput(
                    order_id=order_id,
                    correlation_id=input.correlation_id,
                ),
                start_to_close_timeout=DEFAULT_TIMEOUT,
                retry_policy=DEFAULT_RETRY,
            )

            self._step = "rejecting"

            await workflow.execute_activity(
                reject_order_activity,
                FailOrderInput(
                    order_id=order_id,
                    reason=(
                        "Inventory reservation failed: "
                        f"{exc}"
                    ),
                    correlation_id=input.correlation_id,
                ),
                start_to_close_timeout=DEFAULT_TIMEOUT,
                retry_policy=DEFAULT_RETRY,
            )

            self._step = "rejected"

            return {
                "order_id": order_id,
                "status": "rejected",
                "reason": "inventory_reservation_failed",
            }

        # ============================================================
        # 2. AUTHORIZE PAYMENT
        # ============================================================

        self._step = "authorizing_payment"

        try:
            payment_result = await workflow.execute_activity(
                authorize_payment_activity,
                AuthorizePaymentInput(
                    order_id=order_id,
                    idempotency_key=input.idempotency_key,
                    correlation_id=input.correlation_id,
                ),
                start_to_close_timeout=DEFAULT_TIMEOUT,
                retry_policy=DEFAULT_RETRY,
            )

        except Exception as exc:
            # Inventory succeeded but payment did not.
            #
            # Compensation:
            # release the stock we reserved.
            self._step = "releasing_inventory"

            await workflow.execute_activity(
                release_inventory_activity,
                OrderIdInput(
                    order_id=order_id,
                    correlation_id=input.correlation_id,
                ),
                start_to_close_timeout=DEFAULT_TIMEOUT,
                retry_policy=DEFAULT_RETRY,
            )

            self._step = "cancelling"

            await workflow.execute_activity(
                cancel_order_activity,
                FailOrderInput(
                    order_id=order_id,
                    reason=(
                        "Payment authorization failed: "
                        f"{exc}"
                    ),
                    correlation_id=input.correlation_id,
                ),
                start_to_close_timeout=DEFAULT_TIMEOUT,
                retry_policy=DEFAULT_RETRY,
            )

            self._step = "cancelled"

            return {
                "order_id": order_id,
                "status": "cancelled",
                "reason": "payment_failed",
            }

        payment_id = payment_result[
            "payment_id"
        ]

        # ============================================================
        # 3. SHIPMENT -> NOTIFICATION -> CONFIRMATION
        # ============================================================

        try:
            self._step = "creating_shipment"

            await workflow.execute_activity(
                create_shipment_activity,
                OrderIdInput(
                    order_id=order_id,
                    correlation_id=input.correlation_id,
                ),
                start_to_close_timeout=DEFAULT_TIMEOUT,
                retry_policy=DEFAULT_RETRY,
            )

            self._step = "notifying_customer"

            await workflow.execute_activity(
                notify_customer_activity,
                OrderIdInput(
                    order_id=order_id,
                    correlation_id=input.correlation_id,
                ),
                start_to_close_timeout=DEFAULT_TIMEOUT,
                retry_policy=DEFAULT_RETRY,
            )

            self._step = "confirming_order"

            await workflow.execute_activity(
                confirm_order_activity,
                OrderIdInput(
                    order_id=order_id,
                    correlation_id=input.correlation_id,
                ),
                start_to_close_timeout=DEFAULT_TIMEOUT,
                retry_policy=DEFAULT_RETRY,
            )

        except Exception as exc:
            # Payment already succeeded.
            #
            # We now need compensation for the successful effects:
            #
            # 1. mark the order CANCELLED
            # 2. refund the authorized payment
            # 3. release reserved inventory
            #
            # refund_payment_activity moves CANCELLED -> REFUNDED.

            self._step = "cancelling"

            await workflow.execute_activity(
                cancel_order_activity,
                FailOrderInput(
                    order_id=order_id,
                    reason=(
                        "Post-payment saga step failed: "
                        f"{exc}"
                    ),
                    correlation_id=input.correlation_id,
                ),
                start_to_close_timeout=DEFAULT_TIMEOUT,
                retry_policy=DEFAULT_RETRY,
            )

            self._step = "refunding_payment"

            await workflow.execute_activity(
                refund_payment_activity,
                PaymentIdInput(
                    payment_id=payment_id,
                    correlation_id=input.correlation_id,
                ),
                start_to_close_timeout=DEFAULT_TIMEOUT,
                retry_policy=DEFAULT_RETRY,
            )

            self._step = "releasing_inventory"

            await workflow.execute_activity(
                release_inventory_activity,
                OrderIdInput(
                    order_id=order_id,
                    correlation_id=input.correlation_id,
                ),
                start_to_close_timeout=DEFAULT_TIMEOUT,
                retry_policy=DEFAULT_RETRY,
            )

            self._step = "refunded"

            return {
                "order_id": order_id,
                "status": "refunded",
                "reason": "post_payment_failure",
            }

        # ============================================================
        # SUCCESS
        # ============================================================

        self._step = "completed"

        return {
            "order_id": order_id,
            "payment_id": payment_id,
            "status": "completed",
        }