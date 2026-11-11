"""Build real multi-page PDF files from raw bytes, with no extra dependency.

The ingest tests need actual PDFs, and SPEC assumption A6 rules out downloading
sample files, so this module assembles a minimal, valid PDF by hand: one page
object per page, each with its own content stream and a shared Helvetica font.
The result is a genuine PDF that ``pypdf`` parses like any downloaded file.

Only ASCII text is supported: the pages are used to prove page ordering and
page-level text extraction, not font handling.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

PDF_MAGIC = b"%PDF-1.4\n"

_CATALOG_OBJECT = 1
_PAGES_OBJECT = 2
_FONT_OBJECT = 3
_FIRST_PAGE_OBJECT = 4

_PAGE_WIDTH = 612
_PAGE_HEIGHT = 792


def _escape_pdf_text(text: str) -> str:
    """Escape the characters that terminate a PDF literal string."""
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content_stream(text: str) -> bytes:
    """A content stream that draws ``text`` at the top-left of the page."""
    if not text:
        return b""
    operations = ["BT", "/F1 12 Tf", "14 TL", "72 720 Td"]
    for line in text.splitlines() or [text]:
        operations.append(f"({_escape_pdf_text(line)}) Tj")
        operations.append("T*")
    operations.append("ET")
    return ("\n".join(operations) + "\n").encode("latin-1")


def build_pdf(pages: Iterable[str]) -> bytes:
    """Return the bytes of a valid PDF with one page per entry in ``pages``.

    Page ``n`` (1-based) contains the text from ``pages[n - 1]``; an empty entry
    produces a page with no text at all, which is how an image-only page behaves
    for a text extractor.
    """
    page_texts = list(pages)
    if not page_texts:
        raise ValueError("a PDF needs at least one page")

    objects: dict[int, bytes] = {}
    page_object_numbers: list[int] = []
    next_object_number = _FIRST_PAGE_OBJECT
    for text in page_texts:
        page_object_number = next_object_number
        content_object_number = next_object_number + 1
        next_object_number += 2
        page_object_numbers.append(page_object_number)

        content = _content_stream(text)
        objects[page_object_number] = (
            f"<< /Type /Page /Parent {_PAGES_OBJECT} 0 R "
            f"/MediaBox [0 0 {_PAGE_WIDTH} {_PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 {_FONT_OBJECT} 0 R >> >> "
            f"/Contents {content_object_number} 0 R >>"
        ).encode("ascii")
        objects[content_object_number] = (
            f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"\nendstream"
        )

    objects[_CATALOG_OBJECT] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{number} 0 R" for number in page_object_numbers)
    objects[_PAGES_OBJECT] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_numbers)} >>"
    ).encode("ascii")
    objects[_FONT_OBJECT] = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )

    body = bytearray()
    offsets: dict[int, int] = {}
    cursor = len(PDF_MAGIC)
    for object_number in sorted(objects):
        offsets[object_number] = cursor
        serialized = (
            f"{object_number} 0 obj\n".encode("ascii") + objects[object_number] + b"\nendobj\n"
        )
        body += serialized
        cursor += len(serialized)

    object_count = max(objects) + 1
    xref = [
        b"xref\n",
        f"0 {object_count}\n".encode("ascii"),
        b"0000000000 65535 f \n",
    ]
    for object_number in range(1, object_count):
        xref.append(f"{offsets[object_number]:010d} 00000 n \n".encode("ascii"))
    trailer = (
        f"trailer\n<< /Size {object_count} /Root {_CATALOG_OBJECT} 0 R >>\n"
        f"startxref\n{cursor}\n%%EOF\n"
    ).encode("ascii")

    return PDF_MAGIC + bytes(body) + b"".join(xref) + trailer


def write_pdf(path: Path, pages: Sequence[str]) -> Path:
    """Write ``build_pdf(pages)`` to ``path`` and return the path."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(build_pdf(pages))
    return destination
