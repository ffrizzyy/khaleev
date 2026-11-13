"""Startup migrations (T20): the app applies its own Alembic history.

A fresh install must work with no manual step, so ``create_app``'s lifespan calls
``khaleev.migrations.apply_startup_migrations`` before any request is served.
These tests exercise the helper directly — no server, no lifespan — and pin the
three guarantees the plan asks for:

* the schema comes from the **same Alembic history as the CLI** (never
  ``Base.metadata.create_all``), so the app and ``alembic upgrade head`` cannot
  disagree;
* the step is **idempotent** and never touches rows that are already there, so it
  is safe on every boot;
* it targets **only the data directory it is given**, never one resolved from the
  environment by accident.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import Engine

from khaleev.db import create_engine, create_session_factory
from khaleev.migrations import alembic_config, apply_startup_migrations
from khaleev.models import Document

EXPECTED_TABLES = {
    "documents",
    "chunks",
    "golden_sets",
    "eval_runs",
    "eval_run_entries",
}
ALEMBIC_VERSION_TABLE = "alembic_version"


def _schema(engine: Engine) -> dict[str, set[str]]:
    """Every table and column in the database, for before/after comparisons."""
    inspector = inspect(engine)
    return {
        table: {column["name"] for column in inspector.get_columns(table)}
        for table in inspector.get_table_names()
    }


def _revision(engine: Engine) -> str:
    """The revision recorded in ``alembic_version``."""
    with engine.connect() as connection:
        statement = text(f"SELECT version_num FROM {ALEMBIC_VERSION_TABLE}")
        return str(connection.execute(statement).scalar_one())


def _head_revision() -> str:
    """The head revision of the Alembic history the CLI uses."""
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert head is not None
    return head


@pytest.fixture
def fresh_engine(tmp_path: Path) -> Iterator[Engine]:
    """A brand-new SQLite file with no schema at all."""
    engine = create_engine(tmp_path / "fresh")
    try:
        yield engine
    finally:
        engine.dispose()


def test_apply_startup_migrations_creates_the_schema_on_an_empty_dir(
    tmp_path: Path, fresh_engine: Engine
) -> None:
    assert inspect(fresh_engine).get_table_names() == []

    apply_startup_migrations(tmp_path / "fresh")

    assert set(_schema(fresh_engine)) >= EXPECTED_TABLES
    assert _revision(fresh_engine) == _head_revision()


def test_apply_startup_migrations_targets_only_the_given_data_dir(
    tmp_path: Path,
) -> None:
    """The configured data dir is used, never one resolved from the environment."""
    target = tmp_path / "elsewhere"

    apply_startup_migrations(target)

    assert (target / "khaleev.db").is_file()
    # ``isolated_data_dir`` pins KHALEEV_DATA_DIR to tmp_path; the helper must not
    # have created a database there.
    assert not (tmp_path / "khaleev.db").exists()


def test_apply_startup_migrations_is_idempotent_and_preserves_rows(
    tmp_path: Path, fresh_engine: Engine
) -> None:
    data_dir = tmp_path / "fresh"
    apply_startup_migrations(data_dir)
    with create_session_factory(fresh_engine)() as session:
        session.add(Document(content_hash="kept-hash", title="kept.pdf", page_count=3))
        session.commit()

    schema_before = _schema(fresh_engine)
    revision_before = _revision(fresh_engine)

    # A second boot against the same data dir: at head, so nothing to apply.
    apply_startup_migrations(data_dir)

    assert _revision(fresh_engine) == revision_before
    assert _schema(fresh_engine) == schema_before
    with create_session_factory(fresh_engine)() as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 1
        kept = session.scalar(select(Document))
    assert kept is not None
    assert kept.content_hash == "kept-hash"
    assert kept.title == "kept.pdf"


def test_the_helper_runs_the_same_history_as_the_alembic_cli(tmp_path: Path) -> None:
    """Helper output and ``alembic upgrade head`` output must be identical."""
    startup_dir = tmp_path / "via-startup"
    cli_dir = tmp_path / "via-cli"

    apply_startup_migrations(startup_dir)
    cli_engine = create_engine(cli_dir)
    try:
        with cli_engine.begin() as connection:
            config = alembic_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        cli_schema = _schema(cli_engine)
        cli_revision = _revision(cli_engine)
    finally:
        cli_engine.dispose()

    startup_engine = create_engine(startup_dir)
    try:
        assert _schema(startup_engine) == cli_schema
        assert _revision(startup_engine) == cli_revision == _head_revision()
    finally:
        startup_engine.dispose()


def test_apply_startup_migrations_refuses_to_drift_from_the_orm(tmp_path: Path) -> None:
    """The tables the helper creates are the ORM's tables — not a hand-written copy."""
    from khaleev.models import Base

    apply_startup_migrations(tmp_path / "fresh")

    engine = create_engine(tmp_path / "fresh")
    try:
        created = _schema(engine)
    finally:
        engine.dispose()
    declared = {
        table.name: {column.name for column in table.columns}
        for table in Base.metadata.sorted_tables
    }
    assert {name: columns for name, columns in created.items() if name != "alembic_version"} == (
        declared
    )
