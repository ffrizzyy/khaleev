"""Smoke tests proving the package imports and the offline guard is armed."""

from __future__ import annotations

import socket

import pytest

import khaleev
from khaleev import paths


def test_package_reports_a_version() -> None:
    assert isinstance(khaleev.__version__, str)
    assert khaleev.__version__


def test_default_data_dir_is_absolute_and_under_repo_root() -> None:
    data_dir = paths.default_data_dir()

    assert data_dir.is_absolute()
    assert data_dir.parent == paths.REPO_ROOT
    assert data_dir.name == "data"


def test_socket_guard_blocks_outbound_connections(block_network: type[OSError]) -> None:
    with pytest.raises(block_network, match="blocked in tests"):
        socket.create_connection(("example.com", 80), timeout=0.01)


def test_socket_guard_blocks_raw_connect(block_network: type[OSError]) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        with pytest.raises(block_network, match="blocked in tests"):
            sock.connect(("127.0.0.1", 9))
