"""Page-level PDF text extraction.

Every extracted page keeps the 1-based page number it had in the PDF, in the
PDF's own order, because citations and retrieval are page-addressed (Locked
intent #2, assumption A1). Failures are reported as domain errors — not pypdf
tracebacks — so the API layer can turn them into a clear response.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PyPdfError

PDF_MAGIC = b"%PDF-"
# A PDF header may be preceded by a little junk; readers accept it within 1 KiB.
HEADER_SEARCH_LIMIT = 1024


class IngestError(Exception):
    """Base class for domain errors raised while ingesting a document."""


class NotAPdfError(IngestError):
    """The uploaded bytes are not a PDF."""


class CorruptPdfError(IngestError):
    """The bytes look like a PDF but cannot be read."""


@dataclass(frozen=True, slots=True)
class PageText:
    """The extracted text of one page, tagged with its 1-based page number."""

    page_number: int
    text: str


def _ensure_pdf_header(pdf_bytes: bytes) -> None:
    """Reject anything that is not a PDF before handing it to the parser."""
    if PDF_MAGIC not in pdf_bytes[:HEADER_SEARCH_LIMIT]:
        raise NotAPdfError("Not a PDF: the upload is missing the '%PDF-' header.")


def extract_pages(pdf_bytes: bytes) -> list[PageText]:
    """Extract every page's text, in PDF order, numbered from 1.

    A page with no extractable text (for example a scanned image, which is out of
    scope per SPEC's non-goals) yields an empty ``text``; no placeholder content
    is invented. The page count is ``len`` of the returned list.
    """
    _ensure_pdf_header(pdf_bytes)
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted and not reader.decrypt(""):
            raise CorruptPdfError("Could not read PDF: the document is password-protected.")
        extracted = [page.extract_text() for page in reader.pages]
    except IngestError:
        raise
    except (PyPdfError, ValueError, KeyError, OSError, TypeError) as exc:
        raise CorruptPdfError(f"Could not read PDF: {exc}") from exc

    return [
        PageText(page_number=page_number, text=text or "")
        for page_number, text in enumerate(extracted, start=1)
    ]
