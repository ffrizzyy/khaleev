"""Unit tests for the SQLite pragmas every Khaleev connection must carry.

A live upload once failed with ``database is locked`` while a slow ingest held
the write lock: the engine used the default rollback journal and had no busy
timeout, so an overlapping write raised instead of waiting. These tests pin the
settings that keep one slow ingest from turning a concurrent write into a 500,
and prove the waiting behaviour with two connections on one throwaway file.

Every database here is a ``tmp_path`` SQLite file; no socket is opened.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from khaleev.db import create_engine

#: How long connection A holds the write lock before committing.
WRITER_HOLD_SECONDS = 0.5

#: The competing writer must still be waiting after this much of the hold.
MINIMUM_WAIT_SECONDS = 0.25


def _pragma(connection: object, name: str) -> object:
    return connection.exec_driver_sql(f"PRAGMA {name}").scalar_one()  # type: ignore[attr-defined]


def test_every_connection_reports_wal_journal_and_busy_timeout(tmp_path: Path) -> None:
    """Each connection gets WAL, a 5 s busy timeout, NORMAL sync and foreign keys."""
    engine = create_engine(tmp_path)
    try:
        for _ in range(3):
            with engine.connect() as connection:
                assert str(_pragma(connection, "journal_mode")).lower() == "wal"
                assert _pragma(connection, "busy_timeout") == 5000
                assert _pragma(connection, "synchronous") == 1
                assert _pragma(connection, "foreign_keys") == 1
    finally:
        engine.dispose()


def test_competing_writer_waits_for_the_lock_instead_of_raising(tmp_path: Path) -> None:
    """Connection B's write waits for A's commit rather than failing at once."""
    engine = create_engine(tmp_path)
    try:
        with engine.begin() as setup:
            setup.exec_driver_sql("CREATE TABLE probe (value INTEGER)")

        outcome: dict[str, object] = {}

        def competing_write() -> None:
            started = time.monotonic()
            try:
                with engine.connect() as waiter:
                    waiter.exec_driver_sql("INSERT INTO probe (value) VALUES (2)")
                    waiter.commit()
            except Exception as exc:  # the regression this test exists for
                outcome["error"] = exc
            outcome["elapsed"] = time.monotonic() - started

        with engine.connect() as holder:
            holder.exec_driver_sql("INSERT INTO probe (value) VALUES (1)")
            thread = threading.Thread(target=competing_write)
            thread.start()
            time.sleep(WRITER_HOLD_SECONDS)
            holder.commit()
            thread.join(timeout=WRITER_HOLD_SECONDS + 10)

        assert not thread.is_alive()
        assert "error" not in outcome, outcome.get("error")
        assert float(outcome["elapsed"]) >= MINIMUM_WAIT_SECONDS  # type: ignore[arg-type]

        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT count(*) FROM probe").scalar_one() == 2
    finally:
        engine.dispose()
