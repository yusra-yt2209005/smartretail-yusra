import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker

from app.temporal.workflows import HelloWorkflow


TASK_QUEUE = "smartretail-task-queue"


async def main() -> None:
    temporal_address = os.getenv(
        "TEMPORAL_ADDRESS",
        "localhost:7233",
    )

    client = await Client.connect(
        temporal_address
    )

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[HelloWorkflow],
    )

    print(
        f"Temporal worker listening on '{TASK_QUEUE}'"
    )

    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())