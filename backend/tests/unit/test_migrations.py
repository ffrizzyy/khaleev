"""Migration parity tests for the one-way-door initial schema (T03).

`alembic upgrade head` must produce exactly the tables and columns that the ORM
metadata declares, because every later task builds on this schema and SPEC
forbids changing it afterwards without asking. The tests compare the migrated
database against `Base.metadata` instead of against a hard-coded DDL copy, so
any drift between `0001_initial.py` and the models fails here.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.types import TypeEngine

from khaleev import paths
from khaleev.config import Settings
from khaleev.db import create_engine, create_session_factory, database_path
from khaleev.models import Base, Chunk, Document, EvalRun, EvalRunEntry, GoldenSet

ALEMBIC_INI = paths.BACKEND_ROOT / "alembic.ini"
MIGRATIONS_DIR = paths.PACKAGE_ROOT / "migrations"
ALEMBIC_VERSION_TABLE = "alembic_version"

EXPECTED_TABLES: dict[str, set[str]] = {
    "documents": {"id", "content_hash", "title", "page_count", "created_at"},
    "chunks": {"id", "document_id", "page_number", "chunk_index", "text", "embedding_ref"},
    "golden_sets": {"document_id", "revision", "path", "entries"},
    "eval_runs": {
        "id",
        "document_id",
        "created_at",
        "k",
        "embedder_id",
        "scorer_id",
        "hit_rate",
        "faithfulness",
        "config",
    },
    "eval_run_entries": {
        "run_id",
        "golden_index",
        "hit",
        "answer",
        "claims",
        "supported_claims",
        "faithfulness",
    },
}


def _alembic_config() -> Config:
    """Alembic config bound to this checkout, independent of the cwd."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


def _upgrade_to_head(engine: Engine) -> None:
    """Run the real migration script against ``engine``."""
    with engine.begin() as connection:
        config = _alembic_config()
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def _type_name(type_: TypeEngine[object]) -> str:
    """The declared SQLite column type, without length arguments."""
    return str(type_).split("(")[0].strip().upper()


@pytest.fixture
def migrated_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_engine(tmp_path)
    _upgrade_to_head(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def migrated_session(migrated_engine: Engine):
    with create_session_factory(migrated_engine)() as session:
        yield session


def test_upgraded_tables_match_the_spec(migrated_engine: Engine) -> None:
    actual = {
        name for name in inspect(migrated_engine).get_table_names() if name != ALEMBIC_VERSION_TABLE
    }

    assert actual == set(EXPECTED_TABLES)


@pytest.mark.parametrize("table_name", sorted(EXPECTED_TABLES))
def test_upgraded_columns_match_the_spec(migrated_engine: Engine, table_name: str) -> None:
    columns = {column["name"] for column in inspect(migrated_engine).get_columns(table_name)}

    assert columns == EXPECTED_TABLES[table_name]


def test_upgraded_column_types_match_the_orm(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)

    for table in Base.metadata.sorted_tables:
        migrated = {
            column["name"]: _type_name(column["type"])
            for column in inspector.get_columns(table.name)
        }
        declared = {column.name: _type_name(column.type) for column in table.columns}
        assert migrated == declared, f"column types drift in {table.name}"


def test_upgraded_primary_keys_match_the_orm(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)

    for table in Base.metadata.sorted_tables:
        migrated = inspector.get_pk_constraint(table.name)["constrained_columns"]
        declared = [column.name for column in table.primary_key.columns]
        assert migrated == declared, f"primary key drift in {table.name}"


def test_upgraded_nullability_matches_the_orm(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)

    for table in Base.metadata.sorted_tables:
        for column in inspector.get_columns(table.name):
            declared = table.columns[column["name"]]
            if declared.primary_key:
                # SQLite reports the nullability of primary-key columns inconsistently.
                continue
            assert bool(column["nullable"]) is declared.nullable, (
                f"nullability drift on {table.name}.{column['name']}"
            )


def test_upgrade_head_leaves_no_autogenerate_drift(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        differences = [
            difference
            for difference in compare_metadata(context, Base.metadata)
            if ALEMBIC_VERSION_TABLE not in repr(difference)
        ]

    assert differences == []


def test_alembic_upgrade_head_uses_the_configured_data_dir(tmp_path: Path) -> None:
    config = _alembic_config()

    command.upgrade(config, "head")

    database_file = database_path(Settings(_env_file=None).data_dir)
    assert database_file == tmp_path / "khaleev.db"
    assert database_file.is_file()
    tables = {name for name in inspect(create_engine(tmp_path)).get_table_names()}
    assert set(EXPECTED_TABLES) <= tables


def test_upgrade_head_is_idempotent(migrated_engine: Engine) -> None:
    config = _alembic_config()
    with migrated_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    assert {name for name in inspect(migrated_engine).get_table_names()} >= set(EXPECTED_TABLES)


def test_downgrade_base_removes_every_spec_table(migrated_engine: Engine) -> None:
    config = _alembic_config()
    with migrated_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")

    remaining = {name for name in inspect(migrated_engine).get_table_names()}
    assert remaining & set(EXPECTED_TABLES) == set()


def test_deleting_a_document_cascades_on_the_migrated_schema(
    migrated_engine: Engine, migrated_session
) -> None:
    document = Document(content_hash="migrated-hash", title="Migrated", page_count=2)
    document.chunks = [
        Chunk(page_number=1, chunk_index=0, text="Page one text.", embedding_ref="0")
    ]
    document.golden_set = GoldenSet(
        revision="rev-1",
        path="golden/1.json",
        entries=[{"question": "Q?", "expected_answer": "A", "expected_pages": [1]}],
    )
    run = EvalRun(
        k=5,
        embedder_id="fake-embedder",
        scorer_id="fake-scorer",
        hit_rate=1.0,
        faithfulness=1.0,
        config={"golden_revision": "rev-1"},
    )
    run.entries = [
        EvalRunEntry(
            golden_index=0,
            hit=True,
            answer="A",
            claims=1,
            supported_claims=1,
            faithfulness=1.0,
        )
    ]
    document.eval_runs = [run]
    migrated_session.add(document)
    migrated_session.commit()
    document_id = document.id

    with create_session_factory(migrated_engine)() as session:
        session.execute(delete(Document).where(Document.id == document_id))
        session.commit()

    with create_session_factory(migrated_engine)() as session:
        for model in (Chunk, GoldenSet, EvalRun, EvalRunEntry):
            remaining = session.scalar(select(func.count()).select_from(model))
            assert remaining == 0, f"{model.__tablename__} rows survived the cascade"
