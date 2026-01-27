"""Alembic environment configuration."""

import os
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from src.database.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_url() -> str:
    """Get database URL, preferring DATABASE_URL env var."""
    url = os.environ.get("DATABASE_URL", "")
    if url:
        # Convert async/Heroku URLs to sync psycopg2 format
        url = url.replace("postgresql+asyncpg://", "postgresql://")
        url = url.replace("postgres://", "postgresql://")
        return url
    return config.get_main_option("sqlalchemy.url", "sqlite:///data/ephemeral_vc.db")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(_get_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
