"""Unit tests for prompt building and citation validation (T08).

An answer without page citations is a defect (Locked intent #4), so this module
pins down the two halves of the contract:

* ``build_prompt`` is a pure function that hands the model every retrieved chunk
  with an unambiguous chunk id and 1-based page number, and tells it to tag its
  citations with pages (assumption A2);
* ``parse_citations`` repairs whatever the model actually emitted. It accepts
  the realistic tag shapes (``[page 3]``, ``(p. 3)``, ``[Page 3]``, ``[3]``,
  several pages in one tag), drops pages that were never retrieved, dedupes by
  page, keeps a quote only when the model's own words really occur in the chunk,
  and falls back to the retrieved pages when there is no usable citation at all
  (Boundaries -> Never: never ship an answer without citations).

Everything here is constructed input; the only generator used is
``FakeGenerator`` and no socket is opened.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from khaleev.api.schemas import AnswerResponse, Citation
from khaleev.generation.base import FakeGenerator, GenerationError
from khaleev.generation.citations import parse_citations
from khaleev.generation.prompts import build_prompt
from khaleev.retrieval.search import RetrievedChunk

PAGE_1_TEXT = "Scope of the document: this agreement covers filings and late payments."
PAGE_3_TEXT = "Late filings incur a flat credit penalty per return."
PAGE_5_TEXT = "The penalty is capped at 200 credits for small organisations."

RETRIEVED = (
    RetrievedChunk(
        chunk_id=101,
        page_number=1,
        chunk_index=0,
        text=PAGE_1_TEXT,
        score=0.90,
    ),
    RetrievedChunk(
        chunk_id=102,
        page_number=3,
        chunk_index=0,
        text=PAGE_3_TEXT,
        score=0.80,
    ),
    RetrievedChunk(
        chunk_id=103,
        page_number=5,
        chunk_index=0,
        text=PAGE_5_TEXT,
        score=0.70,
    ),
)


def _pages(citations: list[Citation]) -> list[int]:
    return [citation.page for citation in citations]


# ---------------------------------------------------------------------------
# Citation tag forms the parser must tolerate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tag",
    [
        "[page 3]",
        "[Page 3]",
        "(p. 3)",
        "(page 3)",
        "[3]",
    ],
)
def test_parses_each_realistic_page_tag(tag: str) -> None:
    """Every documented tag shape resolves to the cited retrieved page."""
    answer = f"{PAGE_3_TEXT} {tag}"
    citations = parse_citations(answer, RETRIEVED)

    assert _pages(citations) == [3]
    assert citations[0].quote == PAGE_3_TEXT


def test_parses_multiple_pages_in_one_tag() -> None:
    """One tag may name several pages; each becomes its own citation."""
    citations = parse_citations("See [pages 3, 5] for the rules.", RETRIEVED)

    assert _pages(citations) == [3, 5]


def test_parses_repeated_page_tags_as_one_citation() -> None:
    """Dedupe by page, keeping the first occurrence's order and quote."""
    citations = parse_citations("[page 3] ... and again [page 3].", RETRIEVED)

    assert _pages(citations) == [3]


def test_surrounding_prose_is_ignored() -> None:
    """Only the page tags are parsed; the prose around them is not a citation."""
    answer = (
        "Late filings are penalised. The exact amount is a flat credit penalty "
        "per return. According to the filing rules, this applies to every "
        "return, regardless of size [page 3]."
    )
    citations = parse_citations(answer, RETRIEVED)

    assert _pages(citations) == [3]
    assert citations[0].quote in PAGE_3_TEXT


# ---------------------------------------------------------------------------
# Pages that were never retrieved
# ---------------------------------------------------------------------------


def test_drops_hallucinated_page_but_keeps_valid_one() -> None:
    """A page outside the retrieved set is dropped, not shown as a wrong page."""
    citations = parse_citations("Penalty rules [page 3] and appendix [page 99].", RETRIEVED)

    assert _pages(citations) == [3]


def test_hallucinated_only_falls_back_to_retrieved_pages() -> None:
    """If every cited page is invalid, the answer still ships with real citations."""
    citations = parse_citations("See the appendix [page 99].", RETRIEVED)

    assert _pages(citations) == [1, 3, 5]
    assert all(citation.quote for citation in citations)


def test_no_citation_at_all_falls_back_to_retrieved_pages() -> None:
    """A model that cites nothing yields one citation per retrieved page."""
    citations = parse_citations("Late filings incur a flat credit penalty.", RETRIEVED)

    assert _pages(citations) == [1, 3, 5]
    assert citations[1].quote == PAGE_3_TEXT


def test_fallback_dedupes_retrieved_pages() -> None:
    """Two chunks on the same page produce one fallback citation for that page."""
    repeated = (
        *RETRIEVED,
        RetrievedChunk(
            chunk_id=104,
            page_number=3,
            chunk_index=1,
            text="Additional page-three detail.",
            score=0.60,
        ),
    )

    citations = parse_citations("No tags here.", repeated)

    assert _pages(citations) == [1, 3, 5]


def test_empty_retrieval_and_no_citation_is_an_error() -> None:
    """Citations cannot be fabricated from nothing: empty retrieval is a failure."""
    with pytest.raises(GenerationError):
        parse_citations("No tags here.", ())


# ---------------------------------------------------------------------------
# Quote extraction
# ---------------------------------------------------------------------------


def test_keeps_model_quote_when_verbatim_in_the_chunk() -> None:
    """The model's own quoted words are preserved when they occur in the chunk."""
    answer = f'The rules state "{PAGE_3_TEXT}" [page 3]'
    citations = parse_citations(answer, RETRIEVED)

    assert citations[0].quote == PAGE_3_TEXT


def test_replaces_non_verbatim_quote_with_chunk_snippet() -> None:
    """A fabricated quote is never presented as source text."""
    answer = 'The rules state "This sentence is entirely fabricated." [page 3]'
    citations = parse_citations(answer, RETRIEVED)

    assert "fabricated" not in citations[0].quote.lower()
    assert citations[0].quote in PAGE_3_TEXT


def test_fallback_quote_is_a_deterministic_snippet_of_the_chunk() -> None:
    """The snippet fallback is stable across calls, not random or empty."""
    first = parse_citations("Answer without tags.", RETRIEVED)
    second = parse_citations("Answer without tags.", RETRIEVED)

    assert first == second
    for citation in first:
        chunk_text = {
            1: PAGE_1_TEXT,
            3: PAGE_3_TEXT,
            5: PAGE_5_TEXT,
        }[citation.page]
        assert citation.quote
        assert citation.quote in chunk_text


# ---------------------------------------------------------------------------
# Empty answers are errors, not citation-less answers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("answer", ["", "   ", "\n\t"])
def test_empty_answer_is_an_error(answer: str) -> None:
    with pytest.raises(GenerationError):
        parse_citations(answer, RETRIEVED)


def test_fake_generator_answer_round_trips_through_the_parser() -> None:
    """The injected fake feeds the parser exactly like a real model would."""
    generator = FakeGenerator("The flat penalty applies. [page 3]")
    prompt = build_prompt("What penalty applies?", RETRIEVED)

    answer = generator.generate(prompt)
    citations = parse_citations(answer, RETRIEVED)

    assert generator.prompts == [prompt]
    assert _pages(citations) == [3]


# ---------------------------------------------------------------------------
# Prompt builder: pure, page-tagged, unambiguous
# ---------------------------------------------------------------------------


def test_prompt_lists_every_chunk_with_id_and_page() -> None:
    prompt = build_prompt("What penalty applies to late filings?", RETRIEVED)

    assert "What penalty applies to late filings?" in prompt
    for chunk in RETRIEVED:
        assert f"chunk {chunk.chunk_id}" in prompt
        assert f"page {chunk.page_number}" in prompt
        assert chunk.text in prompt


def test_prompt_requires_page_tagged_citations() -> None:
    prompt = build_prompt("What penalty applies?", RETRIEVED).lower()

    assert "cite" in prompt
    assert "[page" in prompt


def test_prompt_disambiguates_two_chunks_on_the_same_page() -> None:
    two_on_page = (
        RetrievedChunk(chunk_id=201, page_number=2, chunk_index=0, text="First part.", score=0.9),
        RetrievedChunk(chunk_id=202, page_number=2, chunk_index=1, text="Second part.", score=0.8),
    )
    prompt = build_prompt("What does page two say?", two_on_page)

    assert "chunk 201" in prompt
    assert "chunk 202" in prompt
    assert "page 2" in prompt


def test_prompt_builder_is_pure() -> None:
    assert build_prompt("Q?", RETRIEVED) == build_prompt("Q?", RETRIEVED)


@pytest.mark.parametrize("question", ["", "   "])
def test_prompt_rejects_empty_question(question: str) -> None:
    with pytest.raises(ValueError):
        build_prompt(question, RETRIEVED)


def test_prompt_rejects_empty_retrieval() -> None:
    with pytest.raises(ValueError):
        build_prompt("Q?", ())


# ---------------------------------------------------------------------------
# Response schema: a citation can never be missing or page-less
# ---------------------------------------------------------------------------


def test_answer_response_requires_at_least_one_citation() -> None:
    with pytest.raises(ValidationError):
        AnswerResponse(answer="No sources.", citations=[])


def test_answer_response_round_trips_structured_citations() -> None:
    response = AnswerResponse(
        answer="Late filings incur a penalty.",
        citations=[Citation(page=3, quote=PAGE_3_TEXT)],
    )

    assert response.model_dump() == {
        "answer": "Late filings incur a penalty.",
        "citations": [{"page": 3, "quote": PAGE_3_TEXT}],
    }


def test_citation_page_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Citation(page=0, quote="text")
