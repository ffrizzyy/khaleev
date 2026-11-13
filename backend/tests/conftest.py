"""Pytest configuration shared by every Khaleev backend test.

The suite must never reach the network (SPEC AC8, Locked intent #12), so an
autouse guard replaces every outbound socket entry point with a function that
raises before any packet leaves the process. The ``migrated_engine`` and
``migrated_session`` fixtures give integration tests the schema that actually
ships, produced by the app's own migration helper — the same Alembic history as
``alembic upgrade head``, never by the ORM metadata.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from khaleev.db import create_engine, create_session_factory
from khaleev.migrations import upgrade_to_head

KHALEEV_ENV_PREFIX = "KHALEEV_"


class NetworkAccessBlocked(OSError):
    """Raised when a test attempts an outbound network connection."""


def _blocked_call(target: str) -> Callable[..., Any]:
    """Return a callable that refuses the named socket entry point."""

    def guard(*args: Any, **kwargs: Any) -> Any:
        message = f"Network access is blocked in tests (SPEC AC8): attempted {target}"
        raise NetworkAccessBlocked(message)

    return guard


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[NetworkAccessBlocked]]:
    """Block every outbound socket connect for the duration of each test."""
    monkeypatch.setattr(socket, "getaddrinfo", _blocked_call("socket.getaddrinfo"))
    monkeypatch.setattr(socket, "create_connection", _blocked_call("socket.create_connection"))
    monkeypatch.setattr(socket.socket, "connect", _blocked_call("socket.connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked_call("socket.connect_ex"))
    yield NetworkAccessBlocked


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every test at a throwaway data directory (SPEC Boundaries -> Never).

    Inherited ``KHALEEV_*`` variables are dropped so a developer's shell cannot
    change the outcome of a test, and ``KHALEEV_DATA_DIR`` is pinned to
    ``tmp_path`` so nothing can write to the user's real data directory.
    """
    for name in list(os.environ):
        if name.startswith(KHALEEV_ENV_PREFIX):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(f"{KHALEEV_ENV_PREFIX}DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def migrated_engine(isolated_data_dir: Path) -> Iterator[Engine]:
    """A throwaway SQLite database whose schema comes from the Alembic history.

    Integration tests exercise the migrated schema, not one built by
    ``Base.metadata.create_all``, so a drift between the models and the shipped
    migration cannot hide behind a test-only schema. The schema is applied with
    ``khaleev.migrations.upgrade_to_head`` — the same helper the app's startup
    hook calls — so tests and production share one migration code path (T20).
    The data directory is the per-test ``tmp_path``, passed explicitly.
    """
    engine = create_engine(isolated_data_dir)
    try:
        upgrade_to_head(engine)
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def migrated_session(migrated_engine: Engine) -> Iterator[Session]:
    """A session bound to the migrated schema of ``migrated_engine``."""
    with create_session_factory(migrated_engine)() as session:
        yield session
