import uuid

from app.core.idempotency import (
    IDEMPOTENCY_TTL_SECONDS,
    get_stored_response,
    store_response,
)
from app.core.cache import get_redis

# Can store response                  ✅
# Can replay response                 ✅
# Unknown key → None                  ✅
# Same key for different users safe  ✅
# TTL is applied                      ✅

def test_idempotency_response_can_be_stored_and_replayed():
    user_id = uuid.uuid4()

    idempotency_key = (
        f"test-order-{uuid.uuid4()}"
    )

    body = {
        "id": str(uuid.uuid4()),
        "status": "placed",
    }

    store_response(
        user_id=user_id,
        idempotency_key=idempotency_key,
        status_code=202,
        body=body,
    )

    stored = get_stored_response(
        user_id,
        idempotency_key,
    )

    assert stored is not None
    assert stored["status_code"] == 202
    assert stored["body"] == body


def test_unknown_idempotency_key_returns_none():
    result = get_stored_response(
        uuid.uuid4(),
        f"missing-{uuid.uuid4()}",
    )

    assert result is None


def test_same_key_is_scoped_per_user():
    shared_key = f"shared-{uuid.uuid4()}"

    user_one = uuid.uuid4()
    user_two = uuid.uuid4()

    store_response(
        user_id=user_one,
        idempotency_key=shared_key,
        status_code=202,
        body={
            "id": "order-one",
        },
    )

    assert (
        get_stored_response(
            user_one,
            shared_key,
        )["body"]["id"]
        == "order-one"
    )

    assert (
        get_stored_response(
            user_two,
            shared_key,
        )
        is None
    )


def test_idempotency_key_has_24_hour_ttl():
    user_id = uuid.uuid4()
    idempotency_key = f"ttl-{uuid.uuid4()}"

    store_response(
        user_id=user_id,
        idempotency_key=idempotency_key,
        status_code=202,
        body={
            "id": "test-order",
        },
    )

    redis_key = (
        f"idempotency:orders:"
        f"{user_id}:"
        f"{idempotency_key}"
    )

    ttl = get_redis().ttl(
        redis_key
    )

    assert 0 < ttl <= IDEMPOTENCY_TTL_SECONDS