"""Turn uploaded PDF bytes into a stored document, idempotently.

The pipeline is deliberately free of HTTP concerns: routes, CLI commands and
tests all call the same function. It extracts every page, chunks each page
without ever crossing a page boundary, and persists ``(document_id,
page_number, chunk_index, text)`` with a nullable ``embedding_ref`` that a later
task fills in. The contract that already matters here is content-hash dedupe —
identical bytes must never produce a second document, a second stored file, or a
second set of chunks (AC1, F1).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from khaleev import paths
from khaleev.config import Settings
from khaleev.ingest.chunking import chunk_pages
from khaleev.ingest.pdf import extract_pages
from khaleev.models import Chunk, Document

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
    *,
    settings: Settings | None = None,
) -> IngestResult:
    """Store ``pdf_bytes`` once and return its ``documents`` row.

    Identical bytes are deduped by content hash before extraction, so a re-upload
    costs one query and returns the existing row without touching its chunks
    (AC1). New bytes are validated, written to
    ``<data_dir>/pdfs/<content_hash>.pdf``, then committed with their title,
    page count and one ``chunks`` row per page slice. ``embedding_ref`` stays
    ``None`` until the embedding task indexes the chunks.
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
    # The chunks need the generated id, so flush before inserting them.
    session.flush()
    for chunk in chunk_pages(pages, settings):
        session.add(
            Chunk(
                document_id=document.id,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                embedding_ref=None,
            )
        )
    session.commit()
    return IngestResult(document=document, created=True)
