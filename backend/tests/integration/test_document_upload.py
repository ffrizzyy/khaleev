"""Integration tests for uploading a PDF (T04, AC1).

These run against the schema produced by ``alembic upgrade head`` (the
``migrated_engine`` fixture), so the upload path is proven on the database that
actually ships. Every test uses the throwaway data directory the suite-wide
autouse fixture provides, so the user's real data directory is never touched.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fixtures.pdf_factory import build_pdf
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from khaleev.db import create_session_factory
from khaleev.ingest.pdf import CorruptPdfError, NotAPdfError
from khaleev.models import Document
from khaleev.services.documents import upload_document

PAGE_TEXTS = [
    "Late filings incur a 200 credit penalty.",
    "Refunds are processed within ten business days.",
    "Appeals must be filed within thirty days.",
]


def _fixture_pdf() -> bytes:
    return build_pdf(PAGE_TEXTS)


def _document_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Document)) or 0


def _stored_pdfs(data_dir: Path) -> list[Path]:
    return sorted(data_dir.rglob("*.pdf"))


def test_upload_stores_the_pdf_and_creates_one_document(
    migrated_session: Session, tmp_path: Path
) -> None:
    pdf = _fixture_pdf()
    expected_hash = hashlib.sha256(pdf).hexdigest()

    result = upload_document(migrated_session, pdf_bytes=pdf, filename="tax-guide.pdf")

    document = result.document
    assert result.created is True
    assert document.id is not None
    assert document.content_hash == expected_hash
    assert document.title == "tax-guide.pdf"
    assert document.page_count == 3

    stored = tmp_path / "pdfs" / f"{expected_hash}.pdf"
    assert stored.is_file()
    assert stored.read_bytes() == pdf
    assert _document_count(migrated_session) == 1


def test_uploaded_document_survives_a_new_session(migrated_engine: Engine) -> None:
    pdf = _fixture_pdf()

    with create_session_factory(migrated_engine)() as session:
        document_id = upload_document(session, pdf_bytes=pdf, filename="guide.pdf").document.id

    with create_session_factory(migrated_engine)() as session:
        stored = session.get(Document, document_id)
        assert stored is not None
        assert stored.page_count == 3
        assert stored.content_hash == hashlib.sha256(pdf).hexdigest()


def test_reuploading_identical_bytes_returns_the_existing_document(
    migrated_session: Session, tmp_path: Path
) -> None:
    pdf = _fixture_pdf()
    first = upload_document(migrated_session, pdf_bytes=pdf, filename="tax-guide.pdf")

    second = upload_document(migrated_session, pdf_bytes=pdf, filename="tax-guide-copy.pdf")

    assert second.created is False
    assert second.document.id == first.document.id
    assert _document_count(migrated_session) == 1
    assert len(_stored_pdfs(tmp_path)) == 1


def test_dedupe_is_keyed_on_content_not_on_the_filename(migrated_session: Session) -> None:
    pdf = _fixture_pdf()
    first = upload_document(migrated_session, pdf_bytes=pdf, filename="one.pdf")

    second = upload_document(migrated_session, pdf_bytes=pdf, filename="two.pdf")

    assert second.document.id == first.document.id
    assert second.document.title == "one.pdf"


def test_different_bytes_create_separate_documents(
    migrated_session: Session, tmp_path: Path
) -> None:
    first = upload_document(
        migrated_session, pdf_bytes=build_pdf(["First document"]), filename="first.pdf"
    )
    second = upload_document(
        migrated_session, pdf_bytes=build_pdf(["Second document"]), filename="second.pdf"
    )

    assert first.document.id != second.document.id
    assert _document_count(migrated_session) == 2
    assert len(_stored_pdfs(tmp_path)) == 2


def test_non_pdf_upload_is_rejected_without_storing_anything(
    migrated_session: Session, tmp_path: Path
) -> None:
    with pytest.raises(NotAPdfError, match="PDF"):
        upload_document(migrated_session, pdf_bytes=b"plain text", filename="notes.txt")

    assert _document_count(migrated_session) == 0
    assert _stored_pdfs(tmp_path) == []


def test_corrupt_pdf_upload_is_rejected_without_storing_anything(
    migrated_session: Session, tmp_path: Path
) -> None:
    corrupt = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\n"

    with pytest.raises(CorruptPdfError, match="PDF"):
        upload_document(migrated_session, pdf_bytes=corrupt, filename="broken.pdf")

    assert _document_count(migrated_session) == 0
    assert _stored_pdfs(tmp_path) == []


def test_filename_path_components_do_not_leak_into_the_title(migrated_session: Session) -> None:
    result = upload_document(
        migrated_session, pdf_bytes=_fixture_pdf(), filename="uploads/tax-guide.pdf"
    )

    assert result.document.title == "tax-guide.pdf"
