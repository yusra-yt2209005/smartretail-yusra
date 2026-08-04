"""
`Base` is the class every ORM model inherits from. SQLAlchemy tracks
every model that subclasses it in `Base.metadata` — that's what
Alembic reads to know which tables should exist, and what
`selectinload`/relationships resolve against.

This lives in its own tiny file, separate from session.py, because
models/ needs to import Base (to define tables), while session.py
needs settings + the engine (to talk to the database) — keeping them
apart avoids models/ pulling in connection machinery it doesn't need
just to define a table shape.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass