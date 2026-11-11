"""Unit tests for the SQLAlchemy models and their delete semantics.

The schema is the SPEC's data model (`## Stack and constraints`): five tables,
no extra columns. These tests pin the column sets so a later drift is caught,
and they exercise the database-level cascade that a document delete relies on
(AC11). The suite-wide autouse fixture already points ``KHALEEV_DATA_DIR`` at
``tmp_path``, so nothing here can touch the user's real data directory.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from khaleev.config import Settings
from khaleev.db import create_engine, create_session_factory, database_path
from khaleev.models import Base, Chunk, Document, EvalRun, EvalRunEntry, GoldenSet
from khaleev.models.base import utcnow

EXPECTED_COLUMNS: dict[str, set[str]] = {
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


@pytest.fixture
def engine(tmp_path) -> Iterator[Engine]:
    """An engine for a throwaway SQLite file with the ORM schema created."""
    created = create_engine(tmp_path)
    Base.metadata.create_all(created)
    try:
        yield created
    finally:
        created.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with create_session_factory(engine)() as opened:
        yield opened


def _document(content_hash: str = "hash-1") -> Document:
    return Document(content_hash=content_hash, title="Tax filing guide", page_count=9)


def _run(**overrides: object) -> EvalRun:
    values: dict[str, object] = {
        "k": 5,
        "embedder_id": "fake-embedder",
        "scorer_id": "fake-scorer",
        "hit_rate": 0.7,
        "faithfulness": 0.75,
        "config": {"golden_revision": "rev-1", "scorer_version": "1"},
    }
    values.update(overrides)
    return EvalRun(**values)


def _seed_document(session: Session) -> Document:
    """Create a document with one row in every child table."""
    document = _document()
    document.chunks = [
        Chunk(page_number=4, chunk_index=0, text="Late filings incur a penalty.", embedding_ref="0")
    ]
    document.golden_set = GoldenSet(
        revision="rev-1",
        path="golden/1.json",
        entries=[
            {"question": "What penalty applies?", "expected_answer": "200", "expected_pages": [4]}
        ],
    )
    run = _run()
    run.entries = [
        EvalRunEntry(
            golden_index=0,
            hit=True,
            answer="Late filings incur a flat 200 credit penalty.",
            claims=1,
            supported_claims=1,
            faithfulness=1.0,
        )
    ]
    document.eval_runs = [run]
    session.add(document)
    session.commit()
    return document


def test_metadata_defines_exactly_the_spec_tables() -> None:
    assert set(Base.metadata.tables) == set(EXPECTED_COLUMNS)


@pytest.mark.parametrize("table_name", sorted(EXPECTED_COLUMNS))
def test_table_defines_exactly_the_spec_columns(table_name: str) -> None:
    columns = {column.name for column in Base.metadata.tables[table_name].columns}

    assert columns == EXPECTED_COLUMNS[table_name]


def test_golden_sets_are_keyed_by_document() -> None:
    primary_key = [column.name for column in GoldenSet.__table__.primary_key.columns]

    assert primary_key == ["document_id"]


def test_eval_run_entries_are_keyed_by_run_and_golden_index() -> None:
    primary_key = [column.name for column in EvalRunEntry.__table__.primary_key.columns]

    assert primary_key == ["run_id", "golden_index"]


def test_content_hash_is_unique(session: Session) -> None:
    session.add_all([_document("same-hash"), _document("same-hash")])

    with pytest.raises(IntegrityError):
        session.commit()


def test_session_factory_is_tied_to_the_configured_data_dir(tmp_path) -> None:
    settings = Settings(_env_file=None)

    assert database_path(settings.data_dir) == tmp_path / "khaleev.db"

    engine = create_engine(settings.data_dir)
    Base.metadata.create_all(engine)
    with create_session_factory(engine)() as opened:
        opened.add(_document("stored-in-temp-dir"))
        opened.commit()
    with create_session_factory(engine)() as opened:
        stored = opened.scalar(select(func.count()).select_from(Document))
    engine.dispose()

    assert stored == 1
    assert (tmp_path / "khaleev.db").is_file()


def test_sqlite_foreign_keys_are_enforced_on_connect(session: Session) -> None:
    assert session.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_created_at_defaults_to_utc_now(session: Session) -> None:
    document = _document()
    session.add(document)
    session.commit()

    assert document.created_at is not None
    assert utcnow() - document.created_at < timedelta(minutes=1)


def test_numeric_and_json_values_round_trip(session: Session) -> None:
    document = _document()
    run = _run()
    run.entries = [
        EvalRunEntry(
            golden_index=3,
            hit=True,
            answer="Flat 200 credit penalty.",
            claims=2,
            supported_claims=1,
            faithfulness=0.5,
        )
    ]
    document.eval_runs.append(run)
    session.add(document)
    session.commit()
    run_id = run.id
    session.expunge_all()

    stored = session.get(EvalRun, run_id)
    assert stored is not None
    assert isinstance(stored.hit_rate, float)
    assert stored.hit_rate == pytest.approx(0.7)
    assert stored.faithfulness == pytest.approx(0.75)
    assert stored.config == {"golden_revision": "rev-1", "scorer_version": "1"}
    entry = stored.entries[0]
    assert entry.hit is True
    assert entry.golden_index == 3
    assert entry.claims == 2
    assert entry.supported_claims == 1
    assert entry.faithfulness == pytest.approx(0.5)


def test_golden_set_entries_round_trip_as_json(session: Session) -> None:
    document = _seed_document(session)
    document_id = document.id
    session.expunge_all()

    stored = session.get(GoldenSet, document_id)

    assert stored is not None
    assert stored.entries[0]["expected_pages"] == [4]


def test_deleting_a_document_cascades_at_the_database_level(engine: Engine) -> None:
    with create_session_factory(engine)() as session:
        document_id = _seed_document(session).id

    with create_session_factory(engine)() as session:
        session.execute(delete(Document).where(Document.id == document_id))
        session.commit()

    with create_session_factory(engine)() as session:
        assert session.get(Document, document_id) is None
        for model in (Chunk, GoldenSet, EvalRun, EvalRunEntry):
            remaining = session.scalar(select(func.count()).select_from(model))
            assert remaining == 0, f"{model.__tablename__} rows survived the cascade"


def test_deleting_a_document_through_the_orm_cascades_too(engine: Engine) -> None:
    with create_session_factory(engine)() as session:
        document = _seed_document(session)
        session.delete(document)
        session.commit()

    with create_session_factory(engine)() as session:
        for model in (Document, Chunk, GoldenSet, EvalRun, EvalRunEntry):
            remaining = session.scalar(select(func.count()).select_from(model))
            assert remaining == 0, f"{model.__tablename__} rows survived the ORM cascade"
