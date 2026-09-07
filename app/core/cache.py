import hashlib
import json

import redis

from app.core.config import settings


PRODUCT_LIST_CACHE_TTL_SECONDS = 30

_VERSION_KEY = "cache:products:list:version"

_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """
    Return one reusable Redis client for this process.
    """

    global _redis_client

    if _redis_client is None:
        _redis_client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )

    return _redis_client


def bump_product_list_cache_version() -> None:
    """
    Invalidate all existing product-list cache entries.

    We do this by incrementing a version counter rather than scanning
    Redis and deleting every matching cache key.
    """

    get_redis().incr(
        _VERSION_KEY
    )


def get_cached_product_list(
    params: dict,
) -> dict | None:
    """
    Return a cached public product-list response if one exists.
    """

    redis_client = get_redis()

    key = _product_list_key(
        redis_client,
        params,
    )

    cached = redis_client.get(
        key
    )

    if cached is None:
        return None

    return json.loads(
        cached
    )


def set_cached_product_list(
    params: dict,
    payload: dict,
) -> None:
    """
    Cache a public product-list response for 30 seconds.
    """

    redis_client = get_redis()

    key = _product_list_key(
        redis_client,
        params,
    )

    redis_client.setex(
        key,
        PRODUCT_LIST_CACHE_TTL_SECONDS,
        json.dumps(
            payload,
            default=str,
        ),
    )


def _product_list_key(
    redis_client: redis.Redis,
    params: dict,
) -> str:
    """
    Build a deterministic Redis key from:
        cache version + listing parameters.
    """

    version = int(
        redis_client.get(
            _VERSION_KEY
        )
        or 0
    )

    normalized = json.dumps(
        params,
        sort_keys=True,
        default=str,
    )

    digest = hashlib.sha256(
        normalized.encode()
    ).hexdigest()[:16]

    return (
        f"cache:products:list:"
        f"v{version}:"
        f"{digest}"
    )