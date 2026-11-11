"""Pytest configuration shared by every Khaleev backend test.

The suite must never reach the network (SPEC AC8, Locked intent #12), so an
autouse guard replaces every outbound socket entry point with a function that
raises before any packet leaves the process.
"""

from __future__ import annotations

import socket
from collections.abc import Callable, Iterator
from typing import Any

import pytest


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
