import asyncio
import os
import uuid

from temporalio.client import Client

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

    result = await client.execute_workflow(
        HelloWorkflow.run,
        "SmartRetail",
        id=f"hello-{uuid.uuid4()}",
        task_queue=TASK_QUEUE,
    )

    print(f"Workflow result: {result}")


if __name__ == "__main__":
    asyncio.run(main())