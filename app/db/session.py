"""
This module owns the database *connection machinery*: how to actually
open a connection and hand out a unit-of-work session per request. It
knows nothing about products or orders — that separation is what lets
models/ stay purely about table shape, and lets this file stay purely
about plumbing.

engine       -> a pool of actual TCP connections to Postgres. Created once.
SessionLocal -> a factory that hands out a new Session (a "unit of work")
                per request.
get_db       -> the FastAPI dependency every route/service uses to get one.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True) #engine is not one database session per user/request. It manages the underlying connection pool.

# pool_pre_ping=True: SQLAlchemy pings a pooled connection before reusing
# it, and transparently reconnects if Postgres closed it (e.g. it was
# idle and got dropped). Without this, the *first* request after a period
# of inactivity can fail with "server closed the connection unexpectedly".

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    FastAPI dependency. FastAPI calls this once per request, runs the code
    before `yield` to set up, hands the yielded value to the endpoint, and
    after the endpoint returns (success OR exception) runs the code after
    `yield` to tear down. This guarantees the session is always closed —
    no leaked connections even if the endpoint raises.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
