import hashlib
import json
import re

from redis.exceptions import RedisError

from app.core.cache import (
    get_product_list_cache_version,
    get_redis,
)
from app.core.config import settings


def _normalize_question(
    question: str,
) -> str:
    """
    Normalize equivalent questions for deterministic cache keys.
    """

    normalized = question.strip().lower()

    normalized = re.sub(
        r"\s+",
        " ",
        normalized,
    )

    return normalized


def _assistant_cache_key(
    question: str,
    *,
    top_k: int,
) -> str:
    """
    Build a deterministic cache key.

    Catalog version is included so product changes invalidate
    previously cached AI answers.
    """

    normalized = _normalize_question(
        question
    )

    version = (
        get_product_list_cache_version()
    )

    key_material = json.dumps(
        {
            "question": normalized,
            "top_k": top_k,
            "catalog_version": version,
        },
        sort_keys=True,
    )

    digest = hashlib.sha256(
        key_material.encode()
    ).hexdigest()[:24]

    return (
        f"cache:ai:assistant:"
        f"v{version}:"
        f"{digest}"
    )


def get_cached_assistant_answer(
    question: str,
    *,
    top_k: int,
) -> dict | None:
    """
    Return one cached completed assistant response.
    """

    try:
        redis_client = get_redis()

        key = _assistant_cache_key(
            question,
            top_k=top_k,
        )

        cached = redis_client.get(
            key
        )

    except RedisError:
        return None

    if cached is None:
        return None

    try:
        return json.loads(
            cached
        )
    except json.JSONDecodeError:
        return None


def set_cached_assistant_answer(
    question: str,
    *,
    top_k: int,
    payload: dict,
) -> None:
    """
    Cache one successful completed assistant response.
    """

    try:
        redis_client = get_redis()

        key = _assistant_cache_key(
            question,
            top_k=top_k,
        )

        redis_client.setex(
            key,
            settings.ai_answer_cache_ttl_seconds,
            json.dumps(
                payload,
                default=str,
            ),
        )

    except RedisError:
        # Cache failures should not break the assistant.
        return