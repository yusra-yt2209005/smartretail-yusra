import time
import uuid

from redis.exceptions import RedisError

from app.core.cache import get_redis
from app.core.config import settings
from app.core.exceptions import (
    TooManyRequestsError,
)


def enforce_ai_rate_limit(
    user_id: uuid.UUID,
) -> None:
    """
    Apply one fixed-window Redis rate limit per authenticated user.

    Redis key example:
        rate:ai:<user_id>:<window>
    """

    limit = (
        settings.ai_rate_limit_requests
    )

    window_seconds = (
        settings.ai_rate_limit_window_seconds
    )

    current_window = int(
        time.time()
        // window_seconds
    )

    key = (
        f"rate:ai:"
        f"{user_id}:"
        f"{current_window}"
    )

    try:
        redis_client = get_redis()

        count = redis_client.incr(
            key
        )

        if count == 1:
            redis_client.expire(
                key,
                window_seconds + 5,
            )

    except RedisError:
        # Rate limiting should not take the whole AI feature
        # offline if Redis temporarily fails.
        return

    if count > limit:
        raise TooManyRequestsError()