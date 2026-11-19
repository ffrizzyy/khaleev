"""SQLite engine and session factory for the local Khaleev database.

The database file lives inside ``Settings.data_dir`` (SPEC "Local-only data"), so
every caller gets the same file by resolving the configured data directory
rather than the current working directory.

SQLite does not enforce foreign keys unless asked, so ``create_engine`` installs
a ``connect`` listener that turns on ``PRAGMA foreign_keys`` for every
connection. That is what makes ``ON DELETE CASCADE`` from ``documents`` actually
delete chunks, golden sets and eval history (AC11). The same listener puts the
database in WAL mode with a busy timeout, so one slow ingest must not turn a
concurrent write into a 500.
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


def _configure_sqlite_connection(dbapi_connection: Any, _connection_record: Any) -> None:
    """Apply the pragmas every SQLite connection needs.

    Foreign keys make ``ON DELETE CASCADE`` real (AC11). WAL keeps readers out of
    the writer's way, the busy timeout makes a competing writer wait instead of
    failing at once, and ``synchronous=NORMAL`` is the standard WAL companion.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
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
    event.listen(engine, "connect", _configure_sqlite_connection)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory bound to ``engine``."""
    return sessionmaker(bind=engine, expire_on_commit=False)
