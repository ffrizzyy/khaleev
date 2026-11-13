"""Apply the app's Alembic migrations when the API starts (T20).

A fresh install must work with no manual step: before the first request is
served, ``create_app``'s lifespan brings the configured data directory's SQLite
file up to the Alembic head. There are three hard constraints, all of them
tested in ``tests/unit/test_startup_migrations.py`` and
``tests/integration/test_fresh_install.py``:

* **One history.** The step runs the real migration scripts (``alembic upgrade
  head``) — the same history ``uv run alembic upgrade head`` uses. It never calls
  ``Base.metadata.create_all``, so the app and the CLI can never disagree about
  the schema.
* **Idempotent and safe on every boot.** At head, ``upgrade head`` is a no-op. The
  step never downgrades, drops, truncates or re-seeds, so rows written before a
  restart are untouched.
* **Only the configured data dir.** The database URL comes from the ``data_dir``
  argument (``Settings.data_dir`` when called from the app), passed to Alembic as
  a live connection. It does not fall back to an ambient environment variable.

Nothing here imports FastAPI, so the helper can be unit-tested without starting a
server or an event loop.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection
from sqlalchemy.engine import Engine

from khaleev import paths
from khaleev.db import create_engine

#: The Alembic config shipped in ``backend/``; ``script_location`` is absolute.
ALEMBIC_INI = paths.BACKEND_ROOT / "alembic.ini"
MIGRATIONS_DIR = paths.PACKAGE_ROOT / "migrations"

REVISION_HEAD = "head"


def alembic_config(connection: Connection | None = None) -> Config:
    """Alembic config bound to this checkout, optionally for a live connection.

    ``script_location`` is set explicitly so the helper works from any working
    directory. When ``connection`` is given, ``migrations/env.py`` uses it instead
    of resolving ``Settings.data_dir``, which pins the migration to the data
    directory the caller asked for.
    """
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def upgrade_to_head(engine: Engine) -> None:
    """Apply every pending migration to ``engine``'s database.

    At head this is a no-op, so calling it on every boot is safe. It runs in one
    connection/transaction scope owned by Alembic, and it never downgrades.
    """
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection), REVISION_HEAD)


def apply_startup_migrations(data_dir: Path) -> None:
    """Bring ``data_dir``'s SQLite file to the Alembic head, before serving.

    A short-lived engine is used so startup cannot disturb the request-path
    engine pool; the database directory is created if it does not exist yet.
    """
    engine = create_engine(Path(data_dir))
    try:
        upgrade_to_head(engine)
    finally:
        engine.dispose()


__all__ = [
    "ALEMBIC_INI",
    "MIGRATIONS_DIR",
    "REVISION_HEAD",
    "alembic_config",
    "apply_startup_migrations",
    "upgrade_to_head",
]
