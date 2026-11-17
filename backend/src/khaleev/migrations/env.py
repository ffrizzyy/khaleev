"""Alembic environment for Khaleev's local SQLite database.

The database is resolved in this order:

1. a connection handed in by a test through ``config.attributes["connection"]``,
2. an explicit ``sqlalchemy.url`` in the Alembic config,
3. the SQLite file inside ``Settings.data_dir``.

That keeps ``uv run alembic upgrade head`` working with zero configuration while
letting the migration tests run against a throwaway database.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import Connection, Engine
from sqlalchemy import create_engine as create_sqlalchemy_engine
from sqlalchemy.engine import URL

from khaleev.config import load_settings
from khaleev.db import create_engine, database_path
from khaleev.models import Base

config = context.config
target_metadata = Base.metadata


def _settings_database_url() -> URL:
    """Return the URL of the SQLite file inside ``Settings.data_dir``."""
    return URL.create("sqlite+pysqlite", database=str(database_path(load_settings().data_dir)))


def _configured_url() -> str | None:
    """Return the explicitly configured URL, if the caller set one."""
    return config.get_main_option("sqlalchemy.url") or None


def _migration_engine() -> Engine:
    """Return an engine for the configured database or the data directory."""
    configured = _configured_url()
    if configured is not None:
        return create_sqlalchemy_engine(configured)
    return create_engine(load_settings().data_dir)


def run_migrations_offline() -> None:
    """Emit the migration SQL without connecting (``alembic upgrade --sql``)."""
    context.configure(
        url=_configured_url() or _settings_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_with_connection(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply the migrations against a live SQLite connection."""
    connection = config.attributes.get("connection")
    if connection is not None:
        _run_with_connection(connection)
        return

    engine = _migration_engine()
    try:
        with engine.connect() as opened:
            _run_with_connection(opened)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
