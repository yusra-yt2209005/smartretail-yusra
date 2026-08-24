import json
import uuid

from app.core.cache import get_redis


IDEMPOTENCY_TTL_SECONDS = 60 * 60 * 24


def _key(
    user_id: uuid.UUID,
    idempotency_key: str,
) -> str:
    """
    Scope an idempotency key to one customer.

    Two different customers may legitimately generate the same
    client-side idempotency key.
    """
    return (
        f"idempotency:orders:"
        f"{user_id}:"
        f"{idempotency_key}"
    )


def get_stored_response(
    user_id: uuid.UUID,
    idempotency_key: str,
) -> dict | None:
    """
    Return the response previously stored for this logical request.

    Returns None if the key has never been used or has expired.
    """
    raw = get_redis().get(
        _key(
            user_id,
            idempotency_key,
        )
    )

    if raw is None:
        return None

    return json.loads(raw)


def store_response(
    user_id: uuid.UUID,
    idempotency_key: str,
    status_code: int,
    body: dict,
) -> None:
    """
    Store the original HTTP response for 24 hours.

    A retry using the same customer + Idempotency-Key can therefore
    replay the same response instead of creating another order.
    """
    payload = {
        "status_code": status_code,
        "body": body,
    }

    get_redis().setex(
        _key(
            user_id,
            idempotency_key,
        ),
        IDEMPOTENCY_TTL_SECONDS,
        json.dumps(payload),
    )