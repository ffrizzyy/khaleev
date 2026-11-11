"""Turn uploaded PDF bytes into a stored document, idempotently.

The pipeline is deliberately free of HTTP concerns: routes, CLI commands and
tests all call the same function. Chunking and embedding extend this step in
later tasks; the contract that already matters here is content-hash dedupe —
identical bytes must never produce a second document or a second stored file
(AC1, F1).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from khaleev import paths
from khaleev.ingest.pdf import extract_pages
from khaleev.models import Document

# Extensions are PDF-only (SPEC non-goals): Markdown/DOCX/HTML are not ingested.
PDF_SUFFIX = ".pdf"
DEFAULT_TITLE = f"document{PDF_SUFFIX}"


@dataclass(frozen=True, slots=True)
class IngestResult:
    """The document an ingest produced and whether this call created it."""

    document: Document
    created: bool


def content_hash(pdf_bytes: bytes) -> str:
    """SHA-256 of the file bytes: the dedupe key and the stored filename."""
    return hashlib.sha256(pdf_bytes).hexdigest()


def stored_pdf_path(data_dir: Path, digest: str) -> Path:
    """``<data_dir>/pdfs/<content_hash>.pdf`` without creating anything."""
    return paths.DataPaths.from_data_dir(data_dir).pdfs / f"{digest}{PDF_SUFFIX}"


def _title_from_filename(filename: str) -> str:
    """Use the bare file name as the title; never let a path leak into the row."""
    name = Path(filename.replace("\\", "/")).name.strip()
    return name or DEFAULT_TITLE


def _existing_document(session: Session, digest: str) -> Document | None:
    return session.scalar(select(Document).where(Document.content_hash == digest))


def ingest_pdf(
    session: Session,
    pdf_bytes: bytes,
    filename: str,
    data_dir: Path,
) -> IngestResult:
    """Store ``pdf_bytes`` once and return its ``documents`` row.

    Identical bytes are deduped by content hash before extraction, so a re-upload
    costs one query and returns the existing row (AC1). New bytes are validated,
    written to ``<data_dir>/pdfs/<content_hash>.pdf``, then committed with their
    title and page count.
    """
    digest = content_hash(pdf_bytes)
    existing = _existing_document(session, digest)
    if existing is not None:
        return IngestResult(document=existing, created=False)

    pages = extract_pages(pdf_bytes)
    layout = paths.DataPaths.from_data_dir(data_dir).create()
    destination = layout.pdfs / f"{digest}{PDF_SUFFIX}"
    destination.write_bytes(pdf_bytes)

    document = Document(
        content_hash=digest,
        title=_title_from_filename(filename),
        page_count=len(pages),
    )
    session.add(document)
    session.commit()
    return IngestResult(document=document, created=True)
