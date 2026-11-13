"""The offline guarantee is enforced, not assumed (SPEC AC8, Locked intent #12).

``tests/conftest.py`` installs an autouse socket guard for every test. This module
proves the guard is really armed in the suite that runs these tests — a plain
``socket`` call that would otherwise leave the process raises before any packet
is produced. Nothing here needs a network to be present: the guard fires before
DNS resolution or a TCP handshake is attempted.
"""

from __future__ import annotations

import socket

import pytest


def test_the_guard_raises_a_network_access_error(block_network: type[OSError]) -> None:
    assert issubclass(block_network, OSError)


def test_a_real_outbound_connect_is_blocked(block_network: type[OSError]) -> None:
    with pytest.raises(block_network, match="blocked in tests"):
        socket.create_connection(("example.com", 443), timeout=0.01)


def test_dns_resolution_is_blocked(block_network: type[OSError]) -> None:
    with pytest.raises(block_network, match="blocked in tests"):
        socket.getaddrinfo("example.com", 443)


def test_a_raw_socket_connect_is_blocked(block_network: type[OSError]) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        with pytest.raises(block_network, match="blocked in tests"):
            sock.connect(("127.0.0.1", 9))


def test_connect_ex_is_blocked(block_network: type[OSError]) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        with pytest.raises(block_network, match="blocked in tests"):
            sock.connect_ex(("127.0.0.1", 9))
