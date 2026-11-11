"""Unit tests for the settings module and the local data directory layout.

The suite-wide autouse fixture points ``KHALEEV_DATA_DIR`` at ``tmp_path`` for
every test, so constructing settings here can never write into the user's real
data directory (SPEC Boundaries -> Never).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from khaleev import paths
from khaleev.config import Settings


def _clear_khaleev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every inherited KHALEEV_* variable so defaults can be observed."""
    for name in list(os.environ):
        if name.startswith("KHALEEV_"):
            monkeypatch.delenv(name, raising=False)


def test_settings_construct_without_environment_or_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_khaleev_env(monkeypatch)

    settings = Settings()

    assert settings.cloud_api_key is None
    assert settings.cloud_model is None


def test_defaults_match_the_spec() -> None:
    settings = Settings(_env_file=None)

    assert settings.embedder_id == "all-MiniLM-L6-v2"
    assert settings.generator == "ollama"
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.ollama_model == "llama3.1:8b"
    assert settings.cloud_api_key is None
    assert settings.cloud_model is None
    assert settings.retrieval_k == 5
    assert settings.chunk_size == 600
    assert settings.chunk_overlap_ratio == 0.12


def test_data_dir_defaults_to_the_package_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KHALEEV_DATA_DIR", raising=False)

    settings = Settings(_env_file=None)

    assert settings.data_dir == paths.default_data_dir()


def test_data_dir_resolves_to_tmp_path(tmp_path: Path) -> None:
    assert Settings(_env_file=None).data_dir == tmp_path


def test_constructing_settings_does_not_create_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("KHALEEV_DATA_DIR", str(data_dir))

    Settings(_env_file=None)

    assert not data_dir.exists()


def test_golden_dir_sits_under_the_data_dir() -> None:
    settings = Settings(_env_file=None)

    assert settings.golden_dir == settings.data_dir / "golden"


def test_ensure_data_dir_creates_the_layout_idempotently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("KHALEEV_DATA_DIR", str(data_dir))
    settings = Settings(_env_file=None)

    first = settings.ensure_data_dir()
    second = settings.ensure_data_dir()

    assert first == second
    assert first.root == data_dir.resolve()
    assert first.pdfs == first.root / "pdfs"
    assert first.index == first.root / "index"
    assert first.golden == first.root / "golden"
    for directory in (first.root, first.pdfs, first.index, first.golden):
        assert directory.is_absolute()
        assert directory.is_dir()


def test_ensure_data_dir_resolves_a_relative_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KHALEEV_DATA_DIR", "relative-data")

    created = Settings(_env_file=None).ensure_data_dir()

    assert created.root == (tmp_path / "relative-data").resolve()
    assert created.golden.is_dir()


def test_environment_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KHALEEV_CHUNK_SIZE", "700")
    monkeypatch.setenv("KHALEEV_CHUNK_OVERLAP_RATIO", "0.14")
    monkeypatch.setenv("KHALEEV_RETRIEVAL_K", "9")
    monkeypatch.setenv("KHALEEV_GENERATOR", "cloud")
    monkeypatch.setenv("KHALEEV_CLOUD_API_KEY", "test-key")
    monkeypatch.setenv("KHALEEV_CLOUD_MODEL", "test-model")

    settings = Settings(_env_file=None)

    assert settings.chunk_size == 700
    assert settings.chunk_overlap_ratio == 0.14
    assert settings.retrieval_k == 9
    assert settings.generator == "cloud"
    assert settings.cloud_api_key == "test-key"
    assert settings.cloud_model == "test-model"


@pytest.mark.parametrize("chunk_size", [400, 800])
def test_chunk_size_accepts_its_bounds(chunk_size: int) -> None:
    assert Settings(_env_file=None, chunk_size=chunk_size).chunk_size == chunk_size


@pytest.mark.parametrize("chunk_size", [399, 801])
def test_chunk_size_rejects_out_of_range_values(chunk_size: int) -> None:
    with pytest.raises(ValidationError, match="chunk_size"):
        Settings(_env_file=None, chunk_size=chunk_size)


@pytest.mark.parametrize("ratio", [0.10, 0.15])
def test_chunk_overlap_ratio_accepts_its_bounds(ratio: float) -> None:
    settings = Settings(_env_file=None, chunk_overlap_ratio=ratio)

    assert settings.chunk_overlap_ratio == ratio


@pytest.mark.parametrize("ratio", [0.09, 0.16])
def test_chunk_overlap_ratio_rejects_out_of_range_values(ratio: float) -> None:
    with pytest.raises(ValidationError, match="chunk_overlap_ratio"):
        Settings(_env_file=None, chunk_overlap_ratio=ratio)
