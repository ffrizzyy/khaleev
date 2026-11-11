"""Unit tests for page-level PDF text extraction (T04, assumption A1).

The contract: one ``PageText`` per PDF page, in the PDF's own page order, with
1-based page numbers, so a later citation can always name the page it came from
(Locked intent #2). Blank pages must produce no text rather than crashing or
inventing content, and a non-PDF or corrupt upload must surface a domain error.
"""

from __future__ import annotations

import pytest
from fixtures.pdf_factory import build_pdf

from khaleev.ingest.pdf import CorruptPdfError, NotAPdfError, extract_pages


def test_returns_one_page_per_pdf_page_in_pdf_order() -> None:
    pages = extract_pages(build_pdf(["Alpha page one", "Beta page two", "Gamma page three"]))

    assert len(pages) == 3
    assert [page.page_number for page in pages] == [1, 2, 3]
    assert "Alpha page one" in pages[0].text
    assert "Beta page two" in pages[1].text
    assert "Gamma page three" in pages[2].text


def test_page_count_matches_the_number_of_pages() -> None:
    pdf = build_pdf([f"Page {number} of the fixture" for number in range(1, 13)])

    pages = extract_pages(pdf)

    assert len(pages) == 12
    assert [page.page_number for page in pages] == list(range(1, 13))
    assert "Page 12 of the fixture" in pages[-1].text


def test_page_numbers_are_one_based_not_zero_based() -> None:
    pages = extract_pages(build_pdf(["Only page"]))

    assert pages[0].page_number == 1


def test_text_is_kept_with_the_page_it_came_from() -> None:
    pages = extract_pages(build_pdf(["First unique sentence", "Second unique sentence"]))

    assert "Second unique sentence" not in pages[0].text
    assert "First unique sentence" not in pages[1].text


def test_blank_page_yields_empty_text_without_inventing_any() -> None:
    pages = extract_pages(build_pdf(["", "Only text here", ""]))

    assert len(pages) == 3
    assert pages[0].text == ""
    assert "Only text here" in pages[1].text
    assert pages[2].text == ""


def test_rejects_bytes_that_are_not_a_pdf() -> None:
    with pytest.raises(NotAPdfError, match="PDF"):
        extract_pages(b"this is a plain text file, not a PDF")


def test_rejects_an_empty_upload() -> None:
    with pytest.raises(NotAPdfError, match="PDF"):
        extract_pages(b"")


def test_rejects_a_truncated_corrupt_pdf() -> None:
    corrupt = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\n"

    with pytest.raises(CorruptPdfError, match="PDF"):
        extract_pages(corrupt)
