"""Unit tests for retrieval hit rate @ k (T14, AC7, SPEC "Metric definitions").

The metric is page-level: an entry hits when at least one retrieved chunk's
``page_number`` is in the entry's expected set, no matter which part of that page
the chunk came from. Inputs here are constructed by hand - no retrieval is run,
no embedder is called, no database is touched - so the tests pin the arithmetic
and the boundaries (position k vs k+1, duplicate pages, k larger than the chunk
list) without any model in the loop (SPEC AC8, Locked intent #12).

The WORKED EXAMPLE test mirrors SPEC's worked example exactly, including the
page list ``4, 4, 3, 4, 9``.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from khaleev.evals.golden import GoldenEntry
from khaleev.evals.metrics.hit_rate import (
    DEFAULT_K,
    HitRateEntry,
    MetricUndefinedError,
    entry_hit,
    hit_rate,
)
from khaleev.evals.metrics.rounding import format_metric
from khaleev.retrieval.search import RetrievalResult, RetrievedChunk


@dataclass(frozen=True, slots=True)
class Chunk:
    """The one attribute the metric reads from a retrieved chunk."""

    page_number: int


def chunks(*pages: int) -> tuple[Chunk, ...]:
    """Retrieved chunks in rank order, built from their page numbers."""
    return tuple(Chunk(page_number=page) for page in pages)


def entry(expected_pages: list[int], *retrieved_pages: int) -> HitRateEntry:
    return HitRateEntry(expected_pages=expected_pages, retrieved=chunks(*retrieved_pages))


# --- the SPEC worked example ----------------------------------------------


def test_worked_example_expected_page_four_hits() -> None:
    """SPEC: expected ``[4]`` against retrieved pages ``4, 4, 3, 4, 9`` hits."""
    assert entry_hit([4], chunks(4, 4, 3, 4, 9)) is True


def test_worked_example_run_persists_seven_tenths() -> None:
    """SPEC: a run of 10 entries with 7 hits is ``hit_rate@5 = 0.7000``."""
    entries = [entry([4], 4, 4, 3, 4, 9) for _ in range(7)]
    entries += [entry([4], 3, 3, 9, 9, 9) for _ in range(3)]

    value = hit_rate(entries, k=5)

    assert value == 0.7
    assert value == round(7 / 10, 4)
    assert format_metric(value) == "0.7000"


# --- per-entry matching ---------------------------------------------------


def test_accepts_the_real_golden_and_retrieval_types() -> None:
    """The seam T16 uses: a golden entry plus its document-scoped retrieval result."""
    golden = GoldenEntry(
        question="What penalty applies to late filings?",
        expected_answer="Late filings incur a flat 200 credit penalty per return.",
        expected_pages=[4],
    )
    result = RetrievalResult(
        document_id=1,
        k=5,
        chunks=tuple(
            RetrievedChunk(
                chunk_id=chunk_id,
                page_number=page,
                chunk_index=0,
                text="",
                score=1.0 - chunk_id / 10,
            )
            for chunk_id, page in enumerate((4, 4, 3, 4, 9), start=1)
        ),
    )

    assert entry_hit(golden.expected_pages, result.chunks) is True
    assert hit_rate([HitRateEntry(golden.expected_pages, result.chunks)], k=result.k) == 1.0


def test_misses_when_no_retrieved_page_is_expected() -> None:
    assert entry_hit([4], chunks(1, 2, 3, 5, 9)) is False
    assert entry_hit([4], chunks(5)) is False


def test_misses_when_nothing_was_retrieved() -> None:
    assert entry_hit([4], chunks()) is False


def test_page_level_matching_ignores_chunk_position_on_the_page() -> None:
    # Two chunks from page 4: both match, because matching is by page number
    # alone, not by which slice of the page the chunk came from (the chunk_index
    # - here the position in the tuple - is irrelevant).
    assert entry_hit([4], chunks(9, 4)) is True


def test_multiple_expected_pages_match_any_one() -> None:
    assert entry_hit([2, 4], chunks(9, 2)) is True
    assert entry_hit([2, 4], chunks(9, 4, 9)) is True
    assert entry_hit([2, 4], chunks(9, 7, 9)) is False


def test_duplicate_expected_pages_are_a_set() -> None:
    assert entry_hit([4, 4], chunks(4)) is True
    assert entry_hit([4, 4], chunks(3)) is False


def test_duplicate_retrieved_pages_neither_help_nor_hurt() -> None:
    assert entry_hit([4], chunks(4, 4, 4, 4)) is True
    assert entry_hit([4], chunks(3, 3, 3, 3)) is False


def test_an_empty_expected_set_is_invalid_data() -> None:
    with pytest.raises(ValueError, match="expected_pages must not be empty"):
        entry_hit([], chunks(4))


# --- position k boundaries ------------------------------------------------


def test_expected_page_at_position_k_hits() -> None:
    assert hit_rate([entry([4], 9, 8, 4)], k=3) == 1.0


def test_expected_page_at_position_k_plus_one_misses() -> None:
    # Retrieval is score-ordered; only the first k chunks count.
    assert hit_rate([entry([4], 9, 8, 7, 4)], k=3) == 0.0


def test_k_one_only_inspects_the_first_chunk() -> None:
    assert hit_rate([entry([4], 4, 9, 9)], k=1) == 1.0
    assert hit_rate([entry([4], 9, 4, 9)], k=1) == 0.0


def test_k_larger_than_the_number_of_chunks_still_hits() -> None:
    assert hit_rate([entry([4], 9, 4)], k=5) == 1.0


def test_document_with_fewer_chunks_than_k_misses_but_stays_in_the_denominator() -> None:
    entries = [entry([4], 9, 4), entry([4], 9, 9)]

    # k=5 but the second document only has two chunks; it is a miss, not a
    # skipped entry, so the denominator is still the full golden set.
    assert hit_rate(entries, k=5) == 0.5


# --- aggregate arithmetic and rounding ------------------------------------


def test_default_k_is_five() -> None:
    assert DEFAULT_K == 5
    assert hit_rate([entry([4], 9, 9, 9, 9, 4)]) == 1.0


def test_two_of_three_hits_rounds_half_up_to_four_places() -> None:
    entries = [entry([1], 1), entry([1], 1), entry([1], 2)]

    value = hit_rate(entries, k=5)

    assert value == 0.6667
    assert format_metric(value) == "0.6667"


def test_one_of_thirty_two_hits_uses_half_up_not_bankers_rounding() -> None:
    # 1/32 = 0.03125: exactly representable, so half-even (Python's round)
    # drops to 0.0312 while SPEC's half-up rule carries to 0.0313.
    entries = [entry([1], 1)] + [entry([1], 2) for _ in range(31)]

    value = hit_rate(entries, k=5)

    assert round(1 / 32, 4) == 0.0312
    assert value == 0.0313


def test_all_entries_hit() -> None:
    assert hit_rate([entry([1], 1), entry([2], 2)], k=5) == 1.0


def test_no_entries_hit() -> None:
    assert hit_rate([entry([1], 2), entry([2], 1)], k=5) == 0.0


# --- rejected inputs ------------------------------------------------------


def test_empty_golden_set_raises_metric_undefined() -> None:
    with pytest.raises(MetricUndefinedError, match="undefined") as excinfo:
        hit_rate([], k=5)

    message = str(excinfo.value)
    assert "empty" in message
    assert "golden set" in message


def test_metric_undefined_is_a_value_error() -> None:
    assert issubclass(MetricUndefinedError, ValueError)


def test_k_below_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="k must be >= 1"):
        hit_rate([entry([1], 1)], k=0)
