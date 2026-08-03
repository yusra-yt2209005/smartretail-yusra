from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    """Liveness only: "is the process up and responding?" No dependency
    checks -- this is what a container orchestrator polls to decide
    whether to restart the container, so it must be fast and cheap."""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(db: Session = Depends(get_db)):
    """
    Readiness: "is the app able to actually serve traffic right now?"
    Week 1 only has Postgres to check. §3.7's full version (Week 3) adds
    Redis, Kafka and Temporal here too -- same idea, one more check each.
    """
    db.execute(text("SELECT 1"))
    return {"status": "ok", "checks": {"database": "ok"}}
