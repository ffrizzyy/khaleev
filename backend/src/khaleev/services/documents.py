"""Application services for the document library.

This module holds the use cases; it imports no web framework, so the HTTP layer
only has to translate the domain errors it raises into status codes. Everything
here works on a caller-supplied ``Session`` and an explicit data directory, which
is what lets the API tests and the future eval/CLI paths share one implementation.

Three contracts live here:

* **Upload embeds.** ``ingest_pdf`` only writes vectors when it is handed an
  embedder, and an unembedded document retrieves nothing. ``upload_document``
  therefore accepts the embedder and forwards it — the API always passes one
  (``Settings.embedder_id``, or a fake in tests) (T06/T09 gap, AC2).
* **Page text comes from the chunks.** ``GET /api/documents/{id}/pages/{n}`` must
  not re-parse the PDF and must not join pages, so the text is rebuilt from that
  page's stored chunks, undo-ing the chunk overlap deterministically (Locked
  intent #2).
* **Delete is complete.** Rows go through the schema's ``ON DELETE CASCADE``;
  the files that no foreign key can reach (index, stored PDF, golden-set JSON)
  are removed explicitly (AC11).
* **The golden set is a file.** Upload seeds an empty golden file so the path
  always exists, and reading it validates the file, refreshes the derived
  ``golden_sets`` row and returns the revision eval runs compare against (T13).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from khaleev.config import Settings
from khaleev.evals import golden
from khaleev.ingest.embedding import Embedder
from khaleev.ingest.pipeline import IngestResult, ingest_pdf, stored_pdf_path
from khaleev.models import Chunk, Document, GoldenSet
from khaleev.retrieval.index import VectorIndex


class DocumentNotFoundError(LookupError):
    """No document with the requested id exists."""


class PageOutOfRangeError(LookupError):
    """The requested page number is outside the document's 1-based page range."""


def _resolve(settings: Settings | None) -> Settings:
    return settings if settings is not None else Settings()


def _resolve_data_dir(data_dir: Path | None, settings: Settings) -> Path:
    return Path(data_dir) if data_dir is not None else settings.data_dir


def upload_document(
    session: Session,
    *,
    pdf_bytes: bytes,
    filename: str,
    data_dir: Path | None = None,
    settings: Settings | None = None,
    embedder: Embedder | None = None,
) -> IngestResult:
    """Validate, store and dedupe one uploaded PDF, embedding its chunks.

    Raises ``khaleev.ingest.pdf.NotAPdfError`` or ``CorruptPdfError`` (both
    ``IngestError``) for input that cannot be ingested. ``data_dir`` defaults to
    ``Settings.data_dir``, which is the per-test temp directory under pytest.

    ``embedder`` is what fills ``chunks.embedding_ref`` and the document's vector
    index; without it the chunks are stored but retrieval cannot find them, so
    every API caller must pass one.
    """
    config = _resolve(settings)
    resolved_dir = _resolve_data_dir(data_dir, config)
    result = ingest_pdf(
        session,
        pdf_bytes,
        filename,
        resolved_dir,
        settings=config,
        embedder=embedder,
    )
    # The golden path must exist for every document, even before the user edits
    # it, so a revision can always be recorded with an eval run (T13, AC10).
    golden.seed_golden_file(resolved_dir, result.document.id)
    return result


def list_documents(session: Session) -> list[Document]:
    """Every stored document, oldest first (the library's display order)."""
    return list(session.scalars(select(Document).order_by(Document.id)))


def get_document(session: Session, document_id: int) -> Document:
    """Return the document row or raise :class:`DocumentNotFoundError`."""
    document = session.get(Document, document_id)
    if document is None:
        raise DocumentNotFoundError(f"document {document_id} does not exist")
    return document


def _configured_overlap(settings: Settings) -> int:
    """The overlap ``khaleev.ingest.chunking`` used for this configuration.

    Mirrors ``chunking._overlap_length`` (kept private there) so reconstruction
    can undo exactly the overlap that ingest introduced: ``round(chunk_size *
    chunk_overlap_ratio)`` clamped to keep the stride positive.
    """
    overlap = round(settings.chunk_size * settings.chunk_overlap_ratio)
    return max(1, min(overlap, settings.chunk_size - 1))


def _longest_shared_overlap(existing: str, chunk_text: str) -> int:
    """Longest suffix of ``existing`` that is also a prefix of ``chunk_text``.

    The fallback when the configured overlap does not match, which happens only
    if the chunking settings changed after the document was ingested. Bounded by
    the shorter of the two strings, and never negative.
    """
    limit = min(len(existing), len(chunk_text))
    for size in range(limit, 0, -1):
        if existing.endswith(chunk_text[:size]):
            return size
    return 0


def reconstruct_page_text(chunks: Iterable[Chunk], settings: Settings | None = None) -> str:
    """Rebuild one page's text from its stored chunks, without re-parsing the PDF.

    Chunks are ordered by ``chunk_index`` and appended with their overlap prefix
    removed, so the result is the page as it was chunked — never a concatenation
    of neighbouring pages, because only chunks of this page are passed in. The
    configured overlap is preferred when it matches, which keeps repeated text
    (``"ababab…"``) from being mistaken for a longer overlap; the longest shared
    suffix is only a fallback.
    """
    config = _resolve(settings)
    overlap = _configured_overlap(config)
    text = ""
    for chunk in sorted(chunks, key=lambda row: (row.chunk_index, row.id or 0)):
        if not chunk.text:
            continue
        if not text:
            text = chunk.text
            continue
        if overlap < len(chunk.text) and text.endswith(chunk.text[:overlap]):
            text += chunk.text[overlap:]
        else:
            text += chunk.text[_longest_shared_overlap(text, chunk.text) :]
    return text


def page_text(
    session: Session,
    document_id: int,
    page_number: int,
    settings: Settings | None = None,
) -> str:
    """Return the extracted text of one page, rebuilt from its stored chunks.

    Raises :class:`DocumentNotFoundError` for an unknown document and
    :class:`PageOutOfRangeError` for a page outside ``1..page_count``. A blank
    page inside the range returns ``""``: it genuinely has no extractable text,
    and inventing any would be a content defect.
    """
    document = get_document(session, document_id)
    if page_number < 1 or page_number > document.page_count:
        raise PageOutOfRangeError(
            f"page {page_number} is outside document {document_id} "
            f"(pages 1-{document.page_count})"
        )
    chunks = session.scalars(
        select(Chunk)
        .where(Chunk.document_id == document_id, Chunk.page_number == page_number)
        .order_by(Chunk.chunk_index, Chunk.id)
    ).all()
    return reconstruct_page_text(chunks, settings)


def get_golden_set(
    session: Session,
    document_id: int,
    *,
    data_dir: Path | None = None,
    settings: Settings | None = None,
) -> golden.GoldenSet:
    """Return the document's validated golden set, refreshing its stored row.

    ``GET /api/documents/{id}/golden`` is read-only for the caller: the JSON file
    is the source of truth, and the ``golden_sets`` row is kept in step with it so
    later eval runs can record the same revision (AC10). Raises
    :class:`DocumentNotFoundError` for an unknown document and the golden-set
    errors from :mod:`khaleev.evals.golden` for a missing, empty or invalid file.
    """
    config = _resolve(settings)
    resolved_dir = _resolve_data_dir(data_dir, config)
    get_document(session, document_id)
    return golden.sync_golden_set(session, resolved_dir, document_id)


def _golden_file(settings: Settings, document_id: int) -> Path:
    """The canonical golden-set file path for one document (T13 seeds this)."""
    return golden.golden_path(settings.data_dir, document_id)


def _is_within(path: Path, root: Path) -> bool:
    """True when ``path`` resolves inside ``root`` — a guard before unlinking."""
    try:
        return path.resolve().is_relative_to(root.resolve())
    except OSError:  # pragma: no cover - only on an unresolvable path
        return False


def _deletable_files(
    session: Session,
    document: Document,
    settings: Settings,
    data_dir: Path,
) -> Sequence[Path]:
    """Every on-disk artifact of ``document`` that no FK cascade can remove."""
    files: list[Path] = [
        VectorIndex(data_dir, document.id).path,
        stored_pdf_path(data_dir, document.content_hash),
        _golden_file(settings, document.id),
    ]
    golden_row = session.get(GoldenSet, document.id)
    if golden_row is not None and golden_row.path:
        recorded = Path(golden_row.path)
        # Only trust a recorded path that is inside the data directory.
        if _is_within(recorded, data_dir):
            files.append(recorded)
    return files


def delete_document(
    session: Session,
    document_id: int,
    *,
    data_dir: Path | None = None,
    settings: Settings | None = None,
) -> None:
    """Delete a document, its rows, its eval history and its files (AC11).

    The row delete cascades to chunks, the golden set, eval runs and eval run
    entries (``PRAGMA foreign_keys`` is on for every connection). The commit
    happens before the files are removed, so a file problem can never leave a
    deleted row pointing at data the user can still see; a missing file is
    treated as already done, never as an error.
    """
    config = _resolve(settings)
    resolved_dir = _resolve_data_dir(data_dir, config)
    document = get_document(session, document_id)
    files = _deletable_files(session, document, config, resolved_dir)

    session.delete(document)
    session.commit()

    for path in files:
        path.unlink(missing_ok=True)


__all__ = [
    "DocumentNotFoundError",
    "PageOutOfRangeError",
    "delete_document",
    "get_document",
    "get_golden_set",
    "list_documents",
    "page_text",
    "reconstruct_page_text",
    "upload_document",
]
