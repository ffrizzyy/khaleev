"""Integration tests for the document library API (T09, AC1, AC11).

The app under test is built by ``create_app`` with an injected ``FakeEmbedder``
and ``FakeGenerator``, against the schema produced by ``alembic upgrade head``
and the throwaway data directory the autouse fixture pins. No test loads a model
and none can reach the network: the suite-wide socket guard would fail the test
first (SPEC AC8, Locked intent #12).

Upload is the one path where the T06 embedding gap could reappear, so it is
tested twice: through the HTTP response and by reading back the stored chunks
and the vector index. Delete is tested for completeness — rows, cascades, index
file, stored PDF and golden-set file (AC11).
"""

from __future__ import annotations

import hashlib
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
from khaleev.generation import FakeGenerator
from khaleev.ingest.embedding import FakeEmbedder
from khaleev.models import Chunk, Document, EvalRun, EvalRunEntry, GoldenSet
from khaleev.retrieval.index import VectorIndex, index_path

PAGE_TEXTS = [
    "Late filings incur a 200 credit penalty per return.",
    "Refunds are processed within ten business days.",
    "Appeals must be filed within thirty days of the notice.",
]


def _fixture_pdf() -> bytes:
    return build_pdf(PAGE_TEXTS)


def _upload(client: ApiClient, pdf: bytes | None = None, name: str = "tax-guide.pdf"):
    return client.post(
        "/api/documents",
        files={"file": (name, _fixture_pdf() if pdf is None else pdf, "application/pdf")},
    )


def _session(engine: Engine) -> Session:
    return create_session_factory(engine)()


def _count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


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


# --- upload ---------------------------------------------------------------


def test_upload_returns_201_with_the_new_document(
    client: ApiClient, migrated_engine: Engine, tmp_path: Path
) -> None:
    pdf = _fixture_pdf()

    response = _upload(client, pdf)

    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], int)
    assert body["title"] == "tax-guide.pdf"
    assert body["page_count"] == len(PAGE_TEXTS)
    stored = tmp_path / "pdfs" / f"{hashlib.sha256(pdf).hexdigest()}.pdf"
    assert stored.read_bytes() == pdf
    with _session(migrated_engine) as session:
        assert _count(session, Document) == 1


def test_upload_embeds_every_chunk_so_retrieval_can_find_it(
    client: ApiClient, migrated_engine: Engine, tmp_path: Path
) -> None:
    document_id = _upload(client).json()["id"]

    with _session(migrated_engine) as session:
        chunks = list(
            session.scalars(
                select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.id)
            )
        )

    assert chunks
    assert all(chunk.embedding_ref is not None for chunk in chunks)
    assert VectorIndex(tmp_path, document_id).path.is_file()
    assert len(VectorIndex(tmp_path, document_id)) == len(chunks)


def test_reuploading_identical_bytes_returns_200_and_the_existing_id(
    client: ApiClient, migrated_engine: Engine, tmp_path: Path
) -> None:
    first = _upload(client, name="tax-guide.pdf")

    second = _upload(client, name="tax-guide-copy.pdf")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    with _session(migrated_engine) as session:
        assert _count(session, Document) == 1
    assert len(list((tmp_path / "pdfs").glob("*.pdf"))) == 1


def test_a_non_pdf_upload_is_400_and_stores_nothing(
    client: ApiClient, migrated_engine: Engine, tmp_path: Path
) -> None:
    response = _upload(client, b"plain text, not a PDF", name="notes.txt")

    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]
    with _session(migrated_engine) as session:
        assert _count(session, Document) == 0
    assert list((tmp_path / "pdfs").glob("*.pdf")) == []


def test_a_corrupt_pdf_upload_is_422_and_stores_nothing(
    client: ApiClient, migrated_engine: Engine, tmp_path: Path
) -> None:
    corrupt = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\n"

    response = _upload(client, corrupt, name="broken.pdf")

    assert response.status_code == 422
    assert "PDF" in response.json()["detail"]
    with _session(migrated_engine) as session:
        assert _count(session, Document) == 0
    assert list((tmp_path / "pdfs").glob("*.pdf")) == []


# --- listing and detail ---------------------------------------------------


def test_listing_without_documents_is_an_empty_list(client: ApiClient) -> None:
    response = client.get("/api/documents")

    assert response.status_code == 200
    assert response.json() == []


def test_listing_returns_every_uploaded_document(client: ApiClient) -> None:
    first = _upload(client).json()["id"]
    second = _upload(client, build_pdf(["A different document"]), name="other.pdf").json()["id"]

    response = client.get("/api/documents")

    assert response.status_code == 200
    body = response.json()
    assert [document["id"] for document in body] == [first, second]
    assert {document["title"] for document in body} == {"tax-guide.pdf", "other.pdf"}
    assert all(document["page_count"] >= 1 for document in body)


def test_detail_returns_the_document(client: ApiClient) -> None:
    uploaded = _upload(client).json()

    response = client.get(f"/api/documents/{uploaded['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == uploaded["id"]
    assert body["title"] == uploaded["title"]
    assert body["page_count"] == uploaded["page_count"]
    assert body["content_hash"] == hashlib.sha256(_fixture_pdf()).hexdigest()


def test_detail_of_an_unknown_document_is_404(client: ApiClient) -> None:
    response = client.get("/api/documents/424242")

    assert response.status_code == 404
    assert "424242" in response.json()["detail"]


# --- page text ------------------------------------------------------------


def test_page_text_is_non_empty_and_comes_from_that_page_only(
    client: ApiClient, migrated_engine: Engine
) -> None:
    document_id = _upload(client).json()["id"]

    response = client.get(f"/api/documents/{document_id}/pages/2")

    assert response.status_code == 200
    body = response.json()
    assert body["page_number"] == 2
    text = body["text"]
    assert "Refunds are processed" in text
    assert "Late filings" not in text
    assert "Appeals must be filed" not in text
    with _session(migrated_engine) as session:
        page_chunks = list(
            session.scalars(
                select(Chunk).where(
                    Chunk.document_id == document_id,
                    Chunk.page_number == 2,
                )
            )
        )
    assert page_chunks
    assert all(chunk.page_number == 2 for chunk in page_chunks)
    assert all(chunk.text in text for chunk in page_chunks)


def test_page_text_reconstructs_a_multi_chunk_page_without_duplicating_overlap(
    client: ApiClient,
) -> None:
    long_page = "Alpha " * 200  # 1200 chars: two full chunks plus a tail at size 600
    document_id = _upload(client, build_pdf([long_page]), name="long.pdf").json()["id"]

    response = client.get(f"/api/documents/{document_id}/pages/1")

    assert response.status_code == 200
    text = response.json()["text"]
    assert len(text) > Settings(_env_file=None).chunk_size
    assert text.count("Alpha") == 200


def test_page_text_of_an_unknown_document_is_404(client: ApiClient) -> None:
    response = client.get("/api/documents/424242/pages/1")

    assert response.status_code == 404


@pytest.mark.parametrize("page_number", [0, len(PAGE_TEXTS) + 1])
def test_page_text_outside_the_document_is_404(client: ApiClient, page_number: int) -> None:
    document_id = _upload(client).json()["id"]

    response = client.get(f"/api/documents/{document_id}/pages/{page_number}")

    assert response.status_code == 404


# --- delete ---------------------------------------------------------------


def test_delete_removes_rows_cascades_and_files(
    client: ApiClient, migrated_engine: Engine, tmp_path: Path
) -> None:
    document_id = _upload(client).json()["id"]
    golden_file = tmp_path / "golden" / f"{document_id}.json"
    golden_file.parent.mkdir(parents=True, exist_ok=True)
    golden_file.write_text("[]", encoding="utf-8")

    with _session(migrated_engine) as session:
        session.add(
            GoldenSet(
                document_id=document_id,
                revision="test-revision",
                path=str(golden_file),
                entries=[],
            )
        )
        run = EvalRun(
            document_id=document_id,
            k=5,
            embedder_id="fake",
            scorer_id="fake",
            hit_rate=0.5,
            faithfulness=0.5,
            config={},
        )
        session.add(run)
        session.flush()
        session.add(
            EvalRunEntry(
                run_id=run.id,
                golden_index=0,
                hit=True,
                answer="a supported answer",
                claims=1,
                supported_claims=1,
                faithfulness=1.0,
            )
        )
        session.commit()

    assert index_path(tmp_path, document_id).is_file()
    stored_pdf = tmp_path / "pdfs" / f"{hashlib.sha256(_fixture_pdf()).hexdigest()}.pdf"
    assert stored_pdf.is_file()

    response = client.delete(f"/api/documents/{document_id}")

    assert response.status_code == 200
    assert response.json() == {"id": document_id, "deleted": True}
    assert client.get("/api/documents").json() == []
    assert client.get(f"/api/documents/{document_id}").status_code == 404
    with _session(migrated_engine) as session:
        for model in (Document, Chunk, GoldenSet, EvalRun, EvalRunEntry):
            assert _count(session, model) == 0, model.__name__
    assert not index_path(tmp_path, document_id).exists()
    assert not stored_pdf.exists()
    assert not golden_file.exists()


def test_delete_of_an_unknown_document_is_404(client: ApiClient) -> None:
    response = client.delete("/api/documents/424242")

    assert response.status_code == 404


def test_reupload_after_delete_starts_fresh(
    client: ApiClient, migrated_engine: Engine, tmp_path: Path
) -> None:
    document_id = _upload(client).json()["id"]
    assert client.delete(f"/api/documents/{document_id}").status_code == 200

    response = _upload(client, name="fresh-copy.pdf")

    assert response.status_code == 201
    assert response.json()["page_count"] == len(PAGE_TEXTS)
    listed = client.get("/api/documents").json()
    assert [document["id"] for document in listed] == [response.json()["id"]]
    with _session(migrated_engine) as session:
        chunks = list(session.scalars(select(Chunk)))
    assert chunks
    assert all(chunk.embedding_ref is not None for chunk in chunks)
    assert index_path(tmp_path, response.json()["id"]).is_file()


# --- config ---------------------------------------------------------------


def test_get_config_exposes_k_embedder_and_generator(client: ApiClient) -> None:
    response = client.get("/api/config")

    assert response.status_code == 200
    body = response.json()
    assert body["k"] == 5
    assert body["embedder"] == "all-MiniLM-L6-v2"
    assert body["generator"] == "ollama"


def test_put_config_updates_and_persists_for_the_process(client: ApiClient) -> None:
    update = client.put(
        "/api/config",
        json={"k": 7, "embedder": "fake-embedder", "generator": "cloud"},
    )

    assert update.status_code == 200
    assert update.json()["k"] == 7
    assert update.json()["embedder"] == "fake-embedder"
    assert update.json()["generator"] == "cloud"
    # No API key is needed to change the config (Locked intent #11).
    assert client.get("/api/config").json() == update.json()


def test_put_config_accepts_a_partial_update(client: ApiClient) -> None:
    client.put("/api/config", json={"embedder": "fake-embedder"})

    response = client.put("/api/config", json={"k": 9})

    assert response.status_code == 200
    body = response.json()
    assert body["k"] == 9
    assert body["embedder"] == "fake-embedder"
    assert body["generator"] == "ollama"


def test_put_config_rejects_an_invalid_k(client: ApiClient) -> None:
    response = client.put("/api/config", json={"k": 0})

    assert response.status_code == 422
