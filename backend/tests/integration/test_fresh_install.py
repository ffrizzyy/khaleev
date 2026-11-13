"""Fresh install (T20): no manual migration step, and a second boot changes nothing.

These tests reproduce the live-run defect where a brand-new data directory
answered the first ``POST /api/documents`` with
``sqlite3.OperationalError: no such table: documents``. They drive the app's
**real lifespan** (the startup hook uvicorn runs), not ``alembic upgrade head``
by hand, so they prove the fix at the only place a user can observe it.

``tests/fixtures/api_client.ApiClient`` uses ``httpx.ASGITransport``, which does
not run lifespan events, so the lifespan is entered explicitly here. The event
loop is created at import time for the same reason as in ``api_client``: starting
a loop inside a test creates its self-pipe with a loopback connect, which the
suite-wide socket guard would (correctly) refuse — that connect is loop
bookkeeping, not the application reaching the network.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI
from fixtures.api_client import ApiClient
from fixtures.pdf_factory import build_pdf
from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import Engine

from khaleev.app import create_app
from khaleev.config import Settings
from khaleev.db import create_engine, create_session_factory
from khaleev.generation import FakeGenerator
from khaleev.ingest.embedding import FakeEmbedder
from khaleev.models import Document

EXPECTED_TABLES = {
    "documents",
    "chunks",
    "golden_sets",
    "eval_runs",
    "eval_run_entries",
}
PAGES = [
    "Late filings incur a 200 credit penalty per return.",
    "Refunds are processed within ten business days.",
]

#: Created before the per-test socket guard patches ``socket``.
_LIFESPAN_LOOP = asyncio.new_event_loop()


@contextmanager
def _running(app: FastAPI) -> Iterator[FastAPI]:
    """Enter and leave the app's real lifespan, as uvicorn does."""
    lifespan = app.router.lifespan_context(app)
    _LIFESPAN_LOOP.run_until_complete(lifespan.__aenter__())
    try:
        yield app
    finally:
        _LIFESPAN_LOOP.run_until_complete(lifespan.__aexit__(None, None, None))


def _build_app() -> FastAPI:
    return create_app(
        settings=Settings(_env_file=None),
        embedder=FakeEmbedder(),
        generator=FakeGenerator(),
    )


def _upload(client: ApiClient):
    return client.post(
        "/api/documents",
        files={"file": ("fresh.pdf", build_pdf(PAGES), "application/pdf")},
    )


def _schema(engine: Engine) -> dict[str, set[str]]:
    inspector = inspect(engine)
    return {
        table: {column["name"] for column in inspector.get_columns(table)}
        for table in inspector.get_table_names()
    }


def _revision(engine: Engine) -> str:
    with engine.connect() as connection:
        return str(
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        )


def test_a_brand_new_data_dir_serves_an_upload_without_manual_migration(
    tmp_path: Path,
) -> None:
    """AC: a fresh install uploads with 201 and no ``no such table`` error."""
    assert not (tmp_path / "khaleev.db").exists()

    app = _build_app()
    with _running(app), ApiClient(app) as client:
        response = _upload(client)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["page_count"] == len(PAGES)
    assert response.text and "no such table" not in response.text

    engine = create_engine(tmp_path)
    try:
        assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
        # The schema is at head, so the CLI has nothing left to do either.
        assert _revision(engine)
    finally:
        engine.dispose()


def test_a_second_boot_keeps_rows_and_the_schema_unchanged(tmp_path: Path) -> None:
    """Booting twice is a no-op: same head, same columns, rows still there."""
    first = _build_app()
    with _running(first), ApiClient(first) as client:
        uploaded = _upload(client).json()

    engine = create_engine(tmp_path)
    try:
        schema_before = _schema(engine)
        revision_before = _revision(engine)
    finally:
        engine.dispose()
    assert "documents" in schema_before

    # A restarted process: a brand-new app object against the same data dir.
    second = _build_app()
    with _running(second), ApiClient(second) as client:
        listed = client.get("/api/documents").json()

    assert [document["id"] for document in listed] == [uploaded["id"]]

    engine = create_engine(tmp_path)
    try:
        assert _schema(engine) == schema_before
        assert _revision(engine) == revision_before
        with create_session_factory(engine)() as session:
            assert session.scalar(select(func.count()).select_from(Document)) == 1
            kept = session.scalar(select(Document))
    finally:
        engine.dispose()
    assert kept is not None
    assert kept.title == "fresh.pdf"
    assert kept.page_count == len(PAGES)
