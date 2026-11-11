"""SQLite engine and session factory for the local Khaleev database.

The database file lives inside ``Settings.data_dir`` (SPEC "Local-only data"), so
every caller gets the same file by resolving the configured data directory
rather than the current working directory.

SQLite does not enforce foreign keys unless asked, so ``create_engine`` installs
a ``connect`` listener that turns on ``PRAGMA foreign_keys`` for every
connection. That is what makes ``ON DELETE CASCADE`` from ``documents`` actually
delete chunks, golden sets and eval history (AC11).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, event
from sqlalchemy import create_engine as create_sqlalchemy_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from khaleev import paths

DB_FILENAME = "khaleev.db"


def database_path(data_dir: Path) -> Path:
    """Return the SQLite file for ``data_dir`` without creating it."""
    return paths.DataPaths.from_data_dir(data_dir).root / DB_FILENAME


def database_url(data_dir: Path) -> URL:
    """Return the SQLAlchemy URL for ``data_dir``'s SQLite file."""
    return URL.create("sqlite+pysqlite", database=str(database_path(data_dir)))


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    """Turn on foreign-key enforcement for one SQLite connection."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_engine(data_dir: Path, *, echo: bool = False) -> Engine:
    """Create an engine for the SQLite file inside ``data_dir``.

    The data directory is created if needed, and every connection enforces
    foreign keys.
    """
    root = paths.DataPaths.from_data_dir(data_dir).root
    root.mkdir(parents=True, exist_ok=True)
    engine = create_sqlalchemy_engine(database_url(root), echo=echo)
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory bound to ``engine``."""
    return sessionmaker(bind=engine, expire_on_commit=False)
