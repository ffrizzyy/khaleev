"""Application services for the document library.

This module holds the use cases; it imports no web framework, so the HTTP layer
only has to translate the domain errors it raises into status codes. The service
grows in T09 (list/detail/delete) without changing the upload contract.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from khaleev.config import Settings
from khaleev.ingest.pipeline import IngestResult, ingest_pdf


def upload_document(
    session: Session,
    *,
    pdf_bytes: bytes,
    filename: str,
    data_dir: Path | None = None,
) -> IngestResult:
    """Validate, store and dedupe one uploaded PDF.

    Raises ``khaleev.ingest.pdf.NotAPdfError`` or ``CorruptPdfError`` (both
    ``IngestError``) for input that cannot be ingested. ``data_dir`` defaults to
    ``Settings.data_dir``, which is the per-test temp directory under pytest.
    """
    resolved_dir = Path(data_dir) if data_dir is not None else Settings().data_dir
    return ingest_pdf(session, pdf_bytes, filename, resolved_dir)
