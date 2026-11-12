"""Integration tests for the read-only golden-set endpoint (T13, F4, AC4).

``GET /api/documents/{id}/golden`` is the only golden-set route in v1: the file on
disk is the source of truth and the UI only reads it. The tests drive the real
app with fake model dependencies, against the migrated schema and the throwaway
data directory the autouse fixture pins, so no model is loaded and no socket is
opened (SPEC AC8).

Error semantics are asserted explicitly because the route has to tell two
"nothing to show" cases apart: an unknown document and no golden file are both
404, while a file that exists but breaks the golden-set rules (including the
empty set a fresh upload seeds) is 422. Deleting a document must remove its
golden file too (AC11).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fixtures.api_client import ApiClient
from fixtures.pdf_factory import build_pdf
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from khaleev.app import create_app
from khaleev.config import Settings
from khaleev.db import create_session_factory
from khaleev.evals.golden import write_golden_file
from khaleev.generation import FakeGenerator
from khaleev.ingest.embedding import FakeEmbedder
from khaleev.models import GoldenSet as GoldenSetRow

SAMPLE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "golden_sample.json"
SAMPLE_PAYLOAD = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def _fixture_pdf() -> bytes:
    return build_pdf(["Late filings incur a 200 credit penalty per return."])


def _upload(client: ApiClient) -> int:
    response = client.post(
        "/api/documents",
        files={"file": ("tax-guide.pdf", _fixture_pdf(), "application/pdf")},
    )
    assert response.status_code == 201
    return int(response.json()["id"])


def _golden_file(data_dir: Path, document_id: int) -> Path:
    return data_dir / "golden" / f"{document_id}.json"


def _session(engine: Engine) -> Session:
    return create_session_factory(engine)()


@pytest.fixture
def app(migrated_engine: Engine) -> FastAPI:
    """The real app with both model-backed dependencies faked."""
    return create_app(
        settings=Settings(_env_file=None),
        embedder=FakeEmbedder(),
        generator=FakeGenerator(),
    )


@pytest.fixture
def client(app: FastAPI) -> Iterator[ApiClient]:
    with ApiClient(app) as client:
        yield client


def test_upload_seeds_an_empty_golden_file_that_the_api_reports_as_empty(
    client: ApiClient, tmp_path: Path
) -> None:
    document_id = _upload(client)

    seeded = _golden_file(tmp_path, document_id)
    assert seeded.is_file()
    assert json.loads(seeded.read_text(encoding="utf-8")) == []

    response = client.get(f"/api/documents/{document_id}/golden")

    assert response.status_code == 422
    assert "empty" in response.json()["detail"]


def test_get_returns_the_validated_golden_set(
    client: ApiClient, migrated_engine: Engine, tmp_path: Path
) -> None:
    document_id = _upload(client)
    golden = write_golden_file(tmp_path, document_id, SAMPLE_PAYLOAD)

    response = client.get(f"/api/documents/{document_id}/golden")

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == document_id
    assert body["revision"] == hashlib.sha256(golden.path.read_bytes()).hexdigest()
    assert body["entries"] == SAMPLE_PAYLOAD
    with _session(migrated_engine) as session:
        stored = session.get(GoldenSetRow, document_id)
        assert stored is not None
        assert stored.revision == body["revision"]
        assert stored.entries == SAMPLE_PAYLOAD


def test_reading_the_same_file_twice_keeps_one_row_and_one_revision(
    client: ApiClient, migrated_engine: Engine, tmp_path: Path
) -> None:
    document_id = _upload(client)
    write_golden_file(tmp_path, document_id, SAMPLE_PAYLOAD)

    first = client.get(f"/api/documents/{document_id}/golden")
    second = client.get(f"/api/documents/{document_id}/golden")

    assert first.status_code == second.status_code == 200
    assert first.json()["revision"] == second.json()["revision"]
    with _session(migrated_engine) as session:
        count = session.scalar(
            select(func.count())
            .select_from(GoldenSetRow)
            .where(GoldenSetRow.document_id == document_id)
        )
    assert count == 1


def test_editing_the_file_surfaces_the_new_revision_and_entries(
    client: ApiClient, tmp_path: Path
) -> None:
    document_id = _upload(client)
    write_golden_file(tmp_path, document_id, SAMPLE_PAYLOAD)
    before = client.get(f"/api/documents/{document_id}/golden").json()

    write_golden_file(tmp_path, document_id, SAMPLE_PAYLOAD[:1])
    after = client.get(f"/api/documents/{document_id}/golden").json()

    assert after["revision"] != before["revision"]
    assert after["entries"] == SAMPLE_PAYLOAD[:1]


def test_get_of_an_unknown_document_is_404(client: ApiClient) -> None:
    response = client.get("/api/documents/424242/golden")

    assert response.status_code == 404
    assert "424242" in response.json()["detail"]


def test_get_without_a_golden_file_is_404(client: ApiClient, tmp_path: Path) -> None:
    document_id = _upload(client)
    _golden_file(tmp_path, document_id).unlink()

    response = client.get(f"/api/documents/{document_id}/golden")

    assert response.status_code == 404
    assert "golden" in response.json()["detail"]
    assert f"{document_id}.json" in response.json()["detail"]


def test_get_with_an_invalid_entry_is_422_naming_the_entry(
    client: ApiClient, tmp_path: Path
) -> None:
    document_id = _upload(client)
    invalid = [{**SAMPLE_PAYLOAD[0], "expected_pages": []}]
    _golden_file(tmp_path, document_id).write_text(json.dumps(invalid), encoding="utf-8")

    response = client.get(f"/api/documents/{document_id}/golden")

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "entry 0" in detail
    assert "expected_pages" in detail


def test_get_with_malformed_json_is_422_naming_the_file(
    client: ApiClient, tmp_path: Path
) -> None:
    document_id = _upload(client)
    _golden_file(tmp_path, document_id).write_text("[{", encoding="utf-8")

    response = client.get(f"/api/documents/{document_id}/golden")

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "JSON" in detail
    assert f"{document_id}.json" in detail


def test_delete_removes_the_golden_file(
    client: ApiClient, migrated_engine: Engine, tmp_path: Path
) -> None:
    document_id = _upload(client)
    write_golden_file(tmp_path, document_id, SAMPLE_PAYLOAD)
    assert client.get(f"/api/documents/{document_id}/golden").status_code == 200

    assert client.delete(f"/api/documents/{document_id}").status_code == 200

    assert not _golden_file(tmp_path, document_id).exists()
    with _session(migrated_engine) as session:
        assert session.get(GoldenSetRow, document_id) is None
    assert client.get(f"/api/documents/{document_id}/golden").status_code == 404
