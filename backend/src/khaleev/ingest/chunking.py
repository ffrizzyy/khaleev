"""Split extracted page text into overlapping, page-bounded chunks.

Chunking is where citation correctness starts, so the invariants are strict:

* a chunk belongs to exactly one page and keeps that 1-based ``page_number``;
  chunks are never merged across pages (Locked intent #2);
* ``chunk_index`` is 0-based and counts the chunks *within* one page, so
  ``(page_number, chunk_index)`` addresses a chunk uniquely;
* every chunk of a page except the last has exactly ``Settings.chunk_size``
  characters, because overlap reduces the stride, never the size;
* consecutive chunks share ``round(chunk_size * chunk_overlap_ratio)``
  characters, and appending each chunk after the first with that prefix removed
  reproduces the page text exactly — no content is dropped or reordered;
* blank or whitespace-only pages emit no chunks at all.

The module is pure: it imports settings and the ``PageText`` value object only,
so unit tests stay fast and no database or HTTP code is loaded.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from khaleev.config import Settings
from khaleev.ingest.pdf import PageText


@dataclass(frozen=True, slots=True)
class PageChunk:
    """A retrievable slice of one page, addressable by ``(page, index)``."""

    page_number: int
    chunk_index: int
    text: str


def _resolve(settings: Settings | None) -> Settings:
    """Use the caller's settings, or the configured defaults."""
    return settings if settings is not None else Settings()


def _overlap_length(settings: Settings) -> int:
    """The number of characters shared by consecutive chunks of a page.

    Derived from the configured ratio and clamped so a chunk always advances:
    the stride is ``chunk_size - overlap`` and must stay positive.
    """
    overlap = round(settings.chunk_size * settings.chunk_overlap_ratio)
    return max(1, min(overlap, settings.chunk_size - 1))


def chunk_page(
    page_number: int,
    text: str,
    settings: Settings | None = None,
) -> list[PageChunk]:
    """Split one page's ``text`` into overlapping chunks tagged with its page.

    ``page_number`` is 1-based (assumption A1); anything smaller raises
    ``ValueError`` rather than producing an unattributable chunk. Empty or
    whitespace-only pages return ``[]`` so no empty chunk ever reaches storage.
    """
    if page_number < 1:
        raise ValueError(f"page_number must be 1-based, got {page_number}")

    config = _resolve(settings)
    if not text.strip():
        return []

    size = config.chunk_size
    stride = size - _overlap_length(config)
    chunks: list[PageChunk] = []
    for chunk_index, start in enumerate(range(0, len(text), stride)):
        end = min(start + size, len(text))
        chunks.append(
            PageChunk(page_number=page_number, chunk_index=chunk_index, text=text[start:end])
        )
        if end >= len(text):
            break
    return chunks


def chunk_pages(
    pages: Iterable[PageText],
    settings: Settings | None = None,
) -> list[PageChunk]:
    """Chunk every page of a document, in page order, with a stable ordering.

    The result is ordered by the input page order and then by ``chunk_index``,
    so it can be persisted and read back deterministically. A blank page
    contributes no chunks, and no chunk ever spans two pages.
    """
    config = _resolve(settings)
    chunks: list[PageChunk] = []
    for page in pages:
        chunks.extend(chunk_page(page.page_number, page.text, config))
    return chunks
