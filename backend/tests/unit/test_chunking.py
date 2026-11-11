"""Unit tests for page-bounded chunking (T05, Locked intent #2).

The contract under test is what makes citations trustworthy:

* a chunk never straddles two pages and always carries its 1-based source page;
* every chunk of a page except the last has the configured size, so retrieval
  granularity is uniform;
* consecutive chunks overlap by the configured ratio, and removing that overlap
  prefix reassembles the page byte for byte — chunking may not drop content;
* no empty chunk is ever emitted, and a blank page emits nothing at all;
* the size and overlap come from ``Settings``, never from module constants.

The pipeline test at the bottom uploads a real multi-page PDF and reads the
``chunks`` table back, because page attribution has to survive storage too.
"""

from __future__ import annotations

import pytest
from fixtures.pdf_factory import build_pdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from khaleev.config import Settings
from khaleev.ingest.chunking import PageChunk, chunk_page, chunk_pages
from khaleev.ingest.pdf import PageText, extract_pages
from khaleev.models import Chunk
from khaleev.services.documents import upload_document

SIZE = 600
RATIO = 0.12
OVERLAP = round(SIZE * RATIO)

WORDS = ("late", "filings", "incur", "a", "flat", "credit", "penalty", "per", "return")


def _settings(chunk_size: int = SIZE, ratio: float = RATIO) -> Settings:
    """Settings isolated from any developer ``.env`` file."""
    return Settings(_env_file=None, chunk_size=chunk_size, chunk_overlap_ratio=ratio)


def _text(length: int) -> str:
    """Deterministic ASCII prose of exactly ``length`` characters."""
    out = ""
    index = 0
    while len(out) < length:
        out += f"{WORDS[index % len(WORDS)]} "
        index += 1
    return out[:length]


def _reassemble(chunks: list[PageChunk]) -> str:
    """Chunk 0 verbatim plus every later chunk with its overlap prefix removed."""
    return chunks[0].text + "".join(chunk.text[OVERLAP:] for chunk in chunks[1:])


def test_chunks_carry_the_source_page_number() -> None:
    chunks = chunk_page(7, _text(1500), _settings())

    assert chunks
    assert {chunk.page_number for chunk in chunks} == {7}


def test_chunk_indices_start_at_zero_and_increase_by_one() -> None:
    chunks = chunk_page(1, _text(3000), _settings())

    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert chunks[0].chunk_index == 0


def test_every_chunk_except_the_last_has_the_configured_size() -> None:
    chunks = chunk_page(1, _text(3000), _settings())

    assert len(chunks) > 1
    assert [len(chunk.text) for chunk in chunks[:-1]] == [SIZE] * (len(chunks) - 1)
    assert len(chunks[-1].text) <= SIZE


def test_consecutive_chunks_overlap_by_the_configured_ratio() -> None:
    chunks = chunk_page(1, _text(3000), _settings())

    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert len(current.text) > OVERLAP
        assert current.text.startswith(previous.text[-OVERLAP:])
        assert previous.text[-OVERLAP:] == current.text[:OVERLAP]


def test_stripping_the_overlap_reassembles_the_page_exactly() -> None:
    text = _text(3000)

    chunks = chunk_page(1, text, _settings())

    assert _reassemble(chunks) == text


def test_reassembly_survives_line_breaks_and_odd_whitespace() -> None:
    text = "\n\n".join(_text(SIZE + 37) for _ in range(4)) + "\n   trailing   \n"

    chunks = chunk_page(2, text, _settings())

    assert _reassemble(chunks) == text


def test_a_page_shorter_than_the_chunk_size_is_one_chunk() -> None:
    text = _text(140)

    chunks = chunk_page(3, text, _settings())

    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].chunk_index == 0


def test_a_page_of_exactly_the_chunk_size_is_one_chunk() -> None:
    text = _text(SIZE)

    chunks = chunk_page(3, text, _settings())

    assert [chunk.text for chunk in chunks] == [text]


@pytest.mark.parametrize("text", ["", "   ", "\n\t \r\n"])
def test_blank_pages_emit_no_chunks(text: str) -> None:
    assert chunk_page(1, text, _settings()) == []


@pytest.mark.parametrize("page_number", [0, -1])
def test_page_numbers_are_one_based(page_number: int) -> None:
    with pytest.raises(ValueError, match="page_number"):
        chunk_page(page_number, _text(100), _settings())


def test_chunking_honours_a_non_default_size_and_ratio() -> None:
    settings = _settings(chunk_size=400, ratio=0.10)
    text = _text(2000)

    chunks = chunk_page(1, text, settings)

    assert [len(chunk.text) for chunk in chunks[:-1]] == [400] * (len(chunks) - 1)
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert previous.text[-40:] == current.text[:40]
    assert chunks[0].text + "".join(chunk.text[40:] for chunk in chunks[1:]) == text


def test_default_settings_supply_the_chunk_size() -> None:
    chunks = chunk_page(1, _text(2000), _settings())

    assert len(chunks[0].text) == Settings(_env_file=None).chunk_size == 600


def test_chunk_pages_walks_pages_in_order_and_restarts_the_index_per_page() -> None:
    pages = [
        PageText(page_number=1, text=_text(1300)),
        PageText(page_number=2, text=_text(700)),
        PageText(page_number=3, text=""),
    ]

    chunks = chunk_pages(pages, _settings())

    per_page = {
        page.page_number: [chunk for chunk in chunks if chunk.page_number == page.page_number]
        for page in pages
    }
    expected_order = [number for number in (1, 2, 3) for _ in per_page[number]]
    assert [chunk.page_number for chunk in chunks] == expected_order
    for page in pages:
        page_chunks = [chunk for chunk in chunks if chunk.page_number == page.page_number]
        if not page.text.strip():
            assert page_chunks == []
            continue
        assert [chunk.chunk_index for chunk in page_chunks] == list(range(len(page_chunks)))
        assert _reassemble(page_chunks) == page.text


def test_chunks_never_contain_text_from_another_page() -> None:
    pages = [
        PageText(page_number=1, text=f"alphabet {_text(900)}"),
        PageText(page_number=2, text=f"betamax {_text(900)}"),
    ]

    chunks = chunk_pages(pages, _settings())

    for chunk in chunks:
        page = pages[chunk.page_number - 1]
        assert chunk.text in page.text
        other = pages[1] if chunk.page_number == 1 else pages[0]
        marker = other.text.split()[0]
        assert marker not in chunk.text


def test_chunking_is_deterministic() -> None:
    text = _text(1800)

    first = chunk_page(4, text, _settings())
    second = chunk_page(4, text, _settings())

    assert first == second


def _long_page(label: str, lines: int = 3) -> str:
    """A page comfortably longer than the default chunk size, with a marker."""
    body = "\n".join(f"{label} line {line}: {_text(280)}" for line in range(lines))
    return f"{label.upper()} PAGE START\n{body}"


def test_ingest_persists_page_attributed_chunks(migrated_session: Session) -> None:
    pdf = build_pdf([_long_page("alpha"), _long_page("beta"), _long_page("gamma")])
    extracted = extract_pages(pdf)

    result = upload_document(migrated_session, pdf_bytes=pdf, filename="guide.pdf")

    stored = list(
        migrated_session.scalars(
            select(Chunk).order_by(Chunk.page_number, Chunk.chunk_index)
        )
    )
    assert stored
    assert {chunk.page_number for chunk in stored} == {1, 2, 3}
    assert all(chunk.document_id == result.document.id for chunk in stored)
    assert all(chunk.text.strip() for chunk in stored)
    assert all(chunk.embedding_ref is None for chunk in stored)

    for page in extracted:
        page_chunks = [chunk for chunk in stored if chunk.page_number == page.page_number]
        assert [chunk.chunk_index for chunk in page_chunks] == list(range(len(page_chunks)))
        assert len(page_chunks) > 1
        rebuilt = page_chunks[0].text + "".join(
            chunk.text[OVERLAP:] for chunk in page_chunks[1:]
        )
        assert rebuilt == page.text


def test_reuploading_the_same_pdf_does_not_duplicate_chunks(migrated_session: Session) -> None:
    pdf = build_pdf([_long_page("alpha"), _long_page("beta")])

    first = upload_document(migrated_session, pdf_bytes=pdf, filename="guide.pdf")
    first_count = len(list(migrated_session.scalars(select(Chunk))))
    second = upload_document(migrated_session, pdf_bytes=pdf, filename="guide-copy.pdf")

    assert second.document.id == first.document.id
    assert len(list(migrated_session.scalars(select(Chunk)))) == first_count
