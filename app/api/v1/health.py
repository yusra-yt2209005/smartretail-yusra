from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from redis import Redis
from confluent_kafka.admin import AdminClient

from app.core.config import settings
from app.db.session import get_db
from app.temporal.client import get_temporal_client


router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    """
    Liveness check.

    Only answers:
        "Is the FastAPI process alive and responding?"

    It deliberately does not check external dependencies.
    """

    return {
        "status": "ok",
    }


@router.get("/health/ready")
async def readiness(
    db: Session = Depends(get_db),
):
    """
    Readiness check.

    Answers:
        "Can SmartRetail actually serve traffic right now?"

    Week 3 requires checking:
    - PostgreSQL
    - Redis
    - Kafka
    - Temporal

    Returns:
    - HTTP 200 when every dependency is reachable.
    - HTTP 503 when at least one dependency is unavailable.
    """

    checks = {
        "database": "ok",
        "redis": "ok",
        "kafka": "ok",
        "temporal": "ok",
    }

    # ---------------------------------------------------------
    # 1. PostgreSQL
    # ---------------------------------------------------------
    try:
        db.execute(
            text("SELECT 1")
        )

    except Exception:
        checks["database"] = "failed"

    # ---------------------------------------------------------
    # 2. Redis
    #
    # The Celery broker is Redis, so this URL already points to
    # the Redis service used by the application.
    # ---------------------------------------------------------
    try:
        redis_client = Redis.from_url(
            settings.celery_broker_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )

        redis_client.ping()

    except Exception:
        checks["redis"] = "failed"

    # ---------------------------------------------------------
    # 3. Kafka
    # ---------------------------------------------------------
    try:
        kafka_admin = AdminClient(
            {
                "bootstrap.servers": (
                    settings.kafka_bootstrap_servers
                ),
            }
        )

        kafka_admin.list_topics(
            timeout=2,
        )

    except Exception:
        checks["kafka"] = "failed"

    # ---------------------------------------------------------
    # 4. Temporal
    #
    # check_health() raises an exception if Temporal cannot be
    # reached, so successful completion means it is healthy.
    # ---------------------------------------------------------
    try:
        temporal_client = (
            await get_temporal_client()
        )

        await (
            temporal_client
            .service_client
            .check_health()
        )

    except Exception:
        checks["temporal"] = "failed"

    # ---------------------------------------------------------
    # Overall readiness
    # ---------------------------------------------------------
    ready = all(
        value == "ok"
        for value in checks.values()
    )

    return JSONResponse(
        status_code=(
            200
            if ready
            else 503
        ),
        content={
            "status": (
                "ready"
                if ready
                else "not_ready"
            ),
            "checks": checks,
        },
    )