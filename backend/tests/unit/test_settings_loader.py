"""Unit tests for the hermetic constructor and the explicit ``.env`` loader.

Locked intent 20 separates two things that used to be one: ``Settings()`` is
**environment-only** — process environment variables plus field defaults, never
a dotenv file — and ``load_settings()`` is the single, explicit reader of
``backend/.env``. The documented configuration path therefore keeps working for
the app and Alembic, while a test that removes every ``KHALEEV_*`` environment
variable observes the real defaults instead of the developer's local key.

Every test here writes its ``.env`` into ``tmp_path`` and ``monkeypatch.chdir``s
there — the documented CWD mechanism, not a test-only switch. Nothing opens a
socket, loads a model, or writes outside ``tmp_path`` (Locked intent #12, AC8).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

import khaleev.app
from khaleev.app import create_app
from khaleev.config import ENV_FILE_NAME, Settings, load_settings

DOTENV_CHUNK_SIZE = 700


def _write_dotenv(directory: Path, content: str) -> Path:
    """Write ``content`` as the working directory's ``.env`` and return its path."""
    dotenv = directory / ENV_FILE_NAME
    dotenv.write_text(content, encoding="utf-8")
    return dotenv


def _bare_settings_calls(source: str) -> list[ast.Call]:
    """Every ``Settings(...)`` call in ``source``, whatever its arguments."""
    tree = ast.parse(source)
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "Settings":
            calls.append(node)
    return calls


def _called_names(source: str) -> set[str]:
    """Names that ``source`` calls, for the loader-usage half of the guard."""
    tree = ast.parse(source)
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def _loaded_names(source: str) -> set[str]:
    """Names that ``source`` mentions at all, import or call."""
    tree = ast.parse(source)
    return {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }


def test_settings_is_hermetic_while_load_settings_reads_the_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_dotenv(
        tmp_path,
        "KHALEEV_CHUNK_SIZE=700\n"
        "KHALEEV_CLOUD_API_KEY=sk-from-dotenv\n",
    )
    monkeypatch.chdir(tmp_path)

    assert Settings().chunk_size == 600
    assert Settings().cloud_api_key is None

    loaded = load_settings()

    assert loaded.chunk_size == DOTENV_CHUNK_SIZE
    assert loaded.cloud_api_key == "sk-from-dotenv"


def _settings_config_keywords(source: str) -> set[str]:
    """The keyword names passed to ``SettingsConfigDict`` in ``source``."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "model_config"
                   for target in node.targets):
            continue
        if isinstance(node.value, ast.Call):
            return {keyword.arg for keyword in node.value.keywords if keyword.arg is not None}
    return set()


def test_model_config_configures_no_env_file_and_keeps_its_other_keys() -> None:
    # pydantic-settings materialises every config key with its default, so the
    # library reports ``env_file: None`` even when the class passes none at all.
    # The fact under test is that no dotenv file is *configured* — a path here
    # would make every ``Settings()`` read it again.
    assert Settings.model_config.get("env_file") is None
    assert Settings.model_config["env_prefix"] == "KHALEEV_"
    assert Settings.model_config["env_file_encoding"] == "utf-8"
    assert Settings.model_config["extra"] == "ignore"

    config_source = Path(khaleev.app.__file__).parent / "config.py"
    assert "env_file" not in _settings_config_keywords(config_source.read_text(encoding="utf-8"))

    assert load_settings.__module__ == "khaleev.config"


def test_keyword_overrides_win_without_disabling_the_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_dotenv(
        tmp_path,
        f"KHALEEV_CHUNK_SIZE={DOTENV_CHUNK_SIZE}\n"
        "KHALEEV_RETRIEVAL_K=7\n",
    )
    monkeypatch.chdir(tmp_path)

    loaded = load_settings(chunk_size=650)

    assert loaded.chunk_size == 650
    assert loaded.retrieval_k == 7


def test_a_malformed_dotenv_raises_instead_of_falling_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_dotenv(tmp_path, "KHALEEV_CHUNK_SIZE=not-a-number\n")
    monkeypatch.chdir(tmp_path)

    assert Settings().chunk_size == 600

    with pytest.raises(ValidationError):
        load_settings()


def test_create_app_default_routes_through_load_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = Settings()
    monkeypatch.setattr(khaleev.app, "load_settings", lambda **kwargs: sentinel)

    application = create_app()

    assert application.state.services.settings is sentinel


def test_create_app_injected_settings_never_consult_the_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail(**kwargs: object) -> Settings:
        raise AssertionError("create_app(settings=...) must not read a dotenv file")

    monkeypatch.setattr(khaleev.app, "load_settings", _fail)
    explicit = Settings()

    application = create_app(settings=explicit)

    assert application.state.services.settings is explicit


def test_create_app_reads_a_dotenv_from_the_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_dotenv(tmp_path, f"KHALEEV_CHUNK_SIZE={DOTENV_CHUNK_SIZE}\n")
    monkeypatch.chdir(tmp_path)

    application = create_app()

    assert application.state.services.settings.chunk_size == DOTENV_CHUNK_SIZE


def test_production_entry_modules_have_no_bare_settings_call() -> None:
    package_dir = Path(khaleev.app.__file__).parent
    modules = {
        "app.py": package_dir / "app.py",
        "migrations/env.py": package_dir / "migrations" / "env.py",
    }

    for label, path in modules.items():
        source = path.read_text(encoding="utf-8")

        assert _bare_settings_calls(source) == [], f"{label} constructs Settings() directly"
        assert "load_settings" in _loaded_names(source), f"{label} does not import the loader"
        assert "load_settings" in _called_names(source), f"{label} does not call the loader"
