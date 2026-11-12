"""Turn a model's page-tagged answer into validated, structured citations (T08).

Models are asked (see ``khaleev.generation.prompts``) to tag every claim with
its source page. They comply imperfectly: sometimes ``[page 3]``, sometimes
``(p. 3)``, sometimes ``[Page 3]`` or a bare ``[3]``; sometimes several pages in
one tag; sometimes a page number that was never in the retrieved context. This
module is the repair layer required by assumption A2 and Boundaries -> Never:

* a cited page that is not among the retrieved chunk pages is **dropped** — the
  UI must never point at a page the answer did not actually use;
* citations are **deduped by page**, first appearance wins;
* a quote is kept only if the model's own words really occur in the cited
  chunk; otherwise a deterministic snippet of that chunk is used, so the quote
  is always real source text;
* when no usable citation survives (none emitted, or every one hallucinated),
  the answer still ships with one citation per retrieved page, in retrieval
  order — an answer can never ship without citations (Locked intent #4).

Pure standard library plus the citation schema: no model, no I/O, no network.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from khaleev.api.schemas import Citation
from khaleev.generation.base import GenerationError
from khaleev.retrieval.search import RetrievalResult, RetrievedChunk

#: Longest fallback snippet, in characters, taken from the start of a chunk.
SNIPPET_LIMIT = 200

#: Ranges wider than this are clamped before expansion, so a nonsense tag like
#: ``[1-999999]`` cannot allocate a huge list. Only retrieved pages survive anyway.
MAX_RANGE_EXPANSION = 100

_NUMBER = r"\d+(?:\s*[-\u2013\u2014]\s*\d+)?"
_PAGE_MARKER = r"(?:pages?|pp?\.?)"
_NUMBER_LIST = (
    rf"{_NUMBER}(?:\s*(?:,|;|&|\band\b)\s*(?:{_PAGE_MARKER}\s*)?{_NUMBER})*"
)

#: ``[page 3]``, ``[Page 3]``, ``[pages 3, 5]``, ``[3]``, ``[page 3, page 5]``.
_BRACKET_TAG_RE = re.compile(rf"\[\s*(?:{_PAGE_MARKER}\s*)?({_NUMBER_LIST})\s*\]", re.IGNORECASE)
#: ``(p. 3)``, ``(page 3)``, ``(pages 3, 5)``. A bare ``(2024)`` is not a page tag.
_PAREN_TAG_RE = re.compile(rf"\(\s*{_PAGE_MARKER}\s*({_NUMBER_LIST})\s*\)", re.IGNORECASE)
#: One number or ``start-end`` range inside a tag.
_RANGE_RE = re.compile(r"(\d+)(?:\s*[-\u2013\u2014]\s*(\d+))?")
#: Explicitly quoted spans the model wrote; apostrophes inside words are ignored.
_QUOTED_RE = re.compile(
    r"[\u201c\"](?P<double>[^\u201d\"]{3,400})[\u201d\"]"
    r"|(?<!\w)'(?P<single>[^']{3,400})'(?!\w)"
)
#: Any page tag, used to strip earlier tags out of a candidate quote.
_ANY_TAG_RE = re.compile(rf"\[\s*(?:{_PAGE_MARKER}\s*)?{_NUMBER_LIST}\s*\]", re.IGNORECASE)
_SENTENCE_BOUNDARY_CHARS = (".", "!", "?", "\n")
_QUOTE_TRIM = " \t\r\n\"'\u201c\u201d\u2018\u2019()[],;:-\u2014"


@dataclass(frozen=True, slots=True)
class _Tag:
    """One page number mentioned in the answer, with where it appeared."""

    page: int
    start: int


def _normalise_whitespace(text: str) -> str:
    return " ".join(text.split())


def _pages_in(fragment: str) -> list[int]:
    """Expand ``3``, ``3, 5`` and ``3-5`` into individual page numbers."""
    pages: list[int] = []
    for match in _RANGE_RE.finditer(fragment):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        if end < start:
            start, end = end, start
        if end - start > MAX_RANGE_EXPANSION:
            end = start + MAX_RANGE_EXPANSION
        pages.extend(range(start, end + 1))
    return pages


def _iter_tags(answer: str) -> list[_Tag]:
    """Every page mentioned by a bracketed or parenthesised tag, in text order."""
    found: list[_Tag] = []
    for pattern in (_BRACKET_TAG_RE, _PAREN_TAG_RE):
        for match in pattern.finditer(answer):
            for page in _pages_in(match.group(1)):
                found.append(_Tag(page=page, start=match.start()))
    found.sort(key=lambda tag: tag.start)
    return found


def _first_text_by_page(chunks: Sequence[RetrievedChunk]) -> dict[int, str]:
    """The first retrieved chunk text for each page, in retrieval order."""
    first: dict[int, str] = {}
    for chunk in chunks:
        first.setdefault(chunk.page_number, chunk.text)
    return first


def _all_text_by_page(chunks: Sequence[RetrievedChunk]) -> dict[int, str]:
    """All retrieved text for each page, joined, for verbatim quote checks."""
    collected: dict[int, list[str]] = {}
    for chunk in chunks:
        collected.setdefault(chunk.page_number, []).append(chunk.text)
    return {page: "\n".join(texts) for page, texts in collected.items()}


def snippet(text: str) -> str:
    """A deterministic opening snippet of ``text``, for citation fallbacks."""
    collapsed = _normalise_whitespace(text)
    if len(collapsed) <= SNIPPET_LIMIT:
        return collapsed
    cut = collapsed[:SNIPPET_LIMIT]
    boundary = cut.rfind(" ")
    if boundary > 0:
        cut = cut[:boundary]
    return cut.rstrip(" ,;:-") + "\u2026"


def _is_verbatim(candidate: str, page_text: str) -> bool:
    """True when ``candidate`` really occurs in ``page_text`` (whitespace-normalised)."""
    cleaned = _normalise_whitespace(candidate)
    return len(cleaned) >= 3 and cleaned in _normalise_whitespace(page_text)


def _quote_before_tag(answer: str, tag_start: int, page_text: str) -> str | None:
    """The model's own supporting text for one tag, if it is real source text.

    Two candidates are tried, most explicit first: an explicitly quoted span
    just before the tag, then the clause between the previous sentence boundary
    and the tag. Anything that does not occur verbatim in the cited page's
    retrieved text is rejected, so a fabricated quote never survives.
    """
    preceding = answer[:tag_start]

    for match in reversed(list(_QUOTED_RE.finditer(preceding))):
        candidate = (match.group("double") or match.group("single") or "").strip()
        if candidate and _is_verbatim(candidate, page_text):
            return candidate

    boundary = max(preceding.rfind(char) for char in _SENTENCE_BOUNDARY_CHARS)
    tail = _ANY_TAG_RE.sub("", preceding[boundary + 1 :])
    candidate = tail.strip().strip(_QUOTE_TRIM)
    if candidate and _is_verbatim(candidate, page_text):
        return candidate
    return None


def _as_chunks(retrieved: Sequence[RetrievedChunk] | RetrievalResult) -> tuple[RetrievedChunk, ...]:
    if isinstance(retrieved, RetrievalResult):
        return retrieved.chunks
    return tuple(retrieved)


def parse_citations(
    answer: str,
    retrieved: Sequence[RetrievedChunk] | RetrievalResult,
) -> list[Citation]:
    """Return validated citations for ``answer`` drawn from ``retrieved``.

    An empty or whitespace-only answer raises :class:`GenerationError` — it is a
    generator failure, not an answer without citations. The returned list is
    always non-empty; if the model cited nothing usable, every retrieved page is
    cited with a snippet of its chunk.
    """
    if not answer or not answer.strip():
        raise GenerationError(
            "the generator returned an empty answer; check that the configured model "
            "is running and produced text"
        )

    chunks = _as_chunks(retrieved)
    if not chunks:
        raise GenerationError(
            "cannot validate citations without retrieved chunks; the answer cannot be "
            "grounded in the document"
        )

    all_text = _all_text_by_page(chunks)
    first_text = _first_text_by_page(chunks)

    grouped: dict[int, list[_Tag]] = {}
    page_order: list[int] = []
    for tag in _iter_tags(answer):
        if tag.page not in all_text:
            continue  # hallucinated or out-of-scope page: never surfaced
        if tag.page not in grouped:
            grouped[tag.page] = []
            page_order.append(tag.page)
        grouped[tag.page].append(tag)

    citations: list[Citation] = []
    for page in page_order:
        quote = None
        for tag in grouped[page]:
            quote = _quote_before_tag(answer, tag.start, all_text[page])
            if quote:
                break
        if not quote:
            quote = snippet(first_text[page])
        citations.append(Citation(page=page, quote=quote))

    if citations:
        return citations

    # No usable citation at all: fall back to every retrieved page, in retrieval
    # order, so the answer still ships with real page references.
    for page in dict.fromkeys(chunk.page_number for chunk in chunks):
        citations.append(Citation(page=page, quote=snippet(first_text[page])))
    return citations


__all__ = ["SNIPPET_LIMIT", "parse_citations", "snippet"]
