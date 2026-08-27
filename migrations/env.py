from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db.base import Base
import app.models  # noqa: F401  -- import so every model registers with Base.metadata


config = context.config

# Inject our real DATABASE_URL into Alembic's config instead of
# hardcoding it in alembic.ini. This keeps .env as the single source
# of truth, matching the running FastAPI application.
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# `target_metadata` is what Alembic compares against the real database
# when `--autogenerate` is used.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Generate migration SQL without opening a live database connection.

    Example:
        alembic upgrade head --sql
    """
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Normal migration path: connect to PostgreSQL and execute migrations.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()