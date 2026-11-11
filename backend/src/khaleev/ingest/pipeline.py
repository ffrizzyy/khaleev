"""Turn uploaded PDF bytes into a stored document, idempotently.

The pipeline is deliberately free of HTTP concerns: routes, CLI commands and
tests all call the same function. It extracts every page, chunks each page
without ever crossing a page boundary, and persists ``(document_id,
page_number, chunk_index, text)``. When an ``Embedder`` is supplied it also
embeds those chunks, writes the vectors to the document's FAISS index and stores
the index id in ``chunks.embedding_ref`` (T06); without one the chunks are stored
unembedded, which is what the pure chunking tests exercise.

The contract that already matters here is content-hash dedupe — identical bytes
must never produce a second document, a second stored file, or a second set of
chunks (AC1, F1), and by extension must never duplicate vectors in the index.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from khaleev import paths
from khaleev.config import Settings
from khaleev.ingest.chunking import chunk_pages
from khaleev.ingest.embedding import Embedder
from khaleev.ingest.pdf import extract_pages
from khaleev.models import Chunk, Document
from khaleev.retrieval.index import VectorIndex, embedding_ref

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


def _embed_chunks(embedder: Embedder, chunks: Sequence[Chunk], index: VectorIndex) -> None:
    """Embed ``chunks``, store their vectors and point each row at its vector.

    The FAISS id is the chunk's own primary key, and ``embedding_ref`` records
    that id as text, so a search result maps back to a row — and from there to
    its ``page_number`` — with a single lookup. Both sides are written from the
    same ``ids`` list, so a mismatch between the database and the index is
    impossible without an exception.
    """
    if not chunks:
        return

    vectors = embedder.embed_texts([chunk.text for chunk in chunks])
    if len(vectors) != len(chunks):
        raise ValueError(f"embedder returned {len(vectors)} vectors for {len(chunks)} chunks")

    ids = [int(chunk.id) for chunk in chunks]
    index.add(vectors, ids)
    for chunk, vector_id in zip(chunks, ids, strict=True):
        chunk.embedding_ref = embedding_ref(vector_id)


def ingest_pdf(
    session: Session,
    pdf_bytes: bytes,
    filename: str,
    data_dir: Path,
    *,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
) -> IngestResult:
    """Store ``pdf_bytes`` once and return its ``documents`` row.

    Identical bytes are deduped by content hash before extraction, so a re-upload
    costs one query and returns the existing row without touching its chunks or
    its vectors (AC1). New bytes are validated, written to
    ``<data_dir>/pdfs/<content_hash>.pdf``, then committed with their title,
    page count, one ``chunks`` row per page slice and — when ``embedder`` is
    given — one vector per chunk in ``<data_dir>/index/<document_id>.faiss``
    with the matching ``embedding_ref``.
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
    chunks: list[Chunk] = []
    for chunk in chunk_pages(pages, settings):
        row = Chunk(
            document_id=document.id,
            page_number=chunk.page_number,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            embedding_ref=None,
        )
        session.add(row)
        chunks.append(row)
    if embedder is not None:
        # The rows need their primary keys before they can be index ids.
        session.flush()
        _embed_chunks(embedder, chunks, VectorIndex(layout.root, document.id))
    session.commit()
    return IngestResult(document=document, created=True)
