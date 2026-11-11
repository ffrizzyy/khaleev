"""PDF ingestion machinery: page extraction and the ingest pipeline.

The package is importable without touching the database; ``pipeline`` adds the
storage and dedupe step that turns uploaded bytes into a ``documents`` row.
"""

from __future__ import annotations

from khaleev.ingest.pdf import (
    CorruptPdfError,
    IngestError,
    NotAPdfError,
    PageText,
    extract_pages,
)
from khaleev.ingest.pipeline import IngestResult, content_hash, ingest_pdf, stored_pdf_path

__all__ = [
    "CorruptPdfError",
    "IngestError",
    "IngestResult",
    "NotAPdfError",
    "PageText",
    "content_hash",
    "extract_pages",
    "ingest_pdf",
    "stored_pdf_path",
]
