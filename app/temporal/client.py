from temporalio.client import Client

from app.core.config import settings


_client: Client | None = None


async def get_temporal_client() -> Client:
    """
    Return one reusable Temporal client for this API process.
    """
    global _client

    if _client is None:
        _client = await Client.connect(
            settings.temporal_address,
            namespace=settings.temporal_namespace,
        )

    return _client