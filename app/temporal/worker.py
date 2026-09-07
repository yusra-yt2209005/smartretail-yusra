import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from app.core.config import settings
from app.temporal import activities
from app.temporal.workflows import (
    HelloWorkflow,
    OrderSagaWorkflow,
    ProductPublishingWorkflow,
)
from app.core.logging import configure_logging



logger = logging.getLogger(__name__)


async def connect_to_temporal() -> Client:
    """
    Keep trying to connect to Temporal.

    This is useful in Docker Compose because the worker container may
    start slightly before the Temporal server is ready to accept
    connections.
    """

    while True:
        try:
            client = await Client.connect(
                settings.temporal_address,
                namespace=settings.temporal_namespace,
            )

            logger.info(
                "Connected to Temporal at %s",
                settings.temporal_address,
            )

            return client

        except Exception as exc:
            logger.warning(
                "Temporal is not ready yet: %s. "
                "Retrying in 5 seconds...",
                exc,
            )

            await asyncio.sleep(5)


async def main() -> None:
    configure_logging()
    """
    Connect to Temporal and start a worker listening on the
    SmartRetail task queue.
    """

    client = await connect_to_temporal()

    logger.info(
        "Worker starting on task queue '%s'",
        settings.temporal_task_queue,
    )

    # Our Activities are normal synchronous Python functions:
    #
    #     @activity.defn
    #     def reserve_inventory_activity(...):
    #
    # Therefore Temporal needs a thread executor in which those
    # synchronous Activities can run.
    with ThreadPoolExecutor(
        max_workers=10
    ) as activity_executor:

        worker = Worker(
            client,

            # The worker listens only to tasks placed on this queue.
            task_queue=settings.temporal_task_queue,

            # Every Workflow this worker knows how to execute.
            workflows=[
                HelloWorkflow,
                ProductPublishingWorkflow,
                OrderSagaWorkflow,
            ],

            # Every Activity this worker knows how to execute.
            activities=[
                # ---------------------------------------------
                # Product publishing Activities
                # ---------------------------------------------
                activities.validate_product_activity,
                activities.process_media_activity,
                activities.build_catalog_activity,
                activities.chunk_product_activity,
                activities.embed_product_chunks_activity,
                activities.mark_product_published_activity,
                activities.mark_product_publish_failed_activity,

                # ---------------------------------------------
                # Order saga Activities
                # ---------------------------------------------
                activities.reserve_inventory_activity,
                activities.release_inventory_activity,

                activities.authorize_payment_activity,
                activities.refund_payment_activity,

                activities.create_shipment_activity,
                activities.notify_customer_activity,
                activities.confirm_order_activity,

                activities.reject_order_activity,
                activities.cancel_order_activity,
            ],

            activity_executor=activity_executor,
        )

        # worker.run() keeps this process alive.
        #
        # It continuously waits for Temporal tasks until the container
        # or process is stopped.
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())