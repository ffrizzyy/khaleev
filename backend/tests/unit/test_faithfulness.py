"""Unit tests for answer faithfulness (T15, AC7, SPEC "Metric definitions").

The metric is defined over constructed scorer outputs: total supported claims
divided by total claims across the run, half-up to four decimals, with zero
claims scoring ``0.0`` instead of dividing by zero. The scoring bridge
(``score_answer``) is tested with ``FakeEntailmentScorer`` only, so no model is
loaded and no socket is opened (SPEC AC8, Locked intent #12).
"""

from __future__ import annotations

import pytest

from khaleev.api.schemas import Citation
from khaleev.evals.metrics.faithfulness import (
    FaithfulnessEntry,
    entry_faithfulness,
    faithfulness,
    score_answer,
    score_claims,
)
from khaleev.evals.metrics.rounding import format_metric, round_half_up
from khaleev.evals.scorer import FakeEntailmentScorer
from khaleev.retrieval.search import RetrievedChunk


def chunks() -> tuple[RetrievedChunk, ...]:
    """Two retrieved chunks from different pages, in rank order."""
    return (
        RetrievedChunk(
            chunk_id=1,
            page_number=4,
            chunk_index=0,
            text="Late filings incur a flat 200 credit penalty per return.",
            score=0.9,
        ),
        RetrievedChunk(
            chunk_id=2,
            page_number=9,
            chunk_index=0,
            text="Interest accrues daily on unpaid amounts.",
            score=0.8,
        ),
    )


# --- the SPEC worked example ----------------------------------------------


def test_worked_example_fifteen_of_twenty_claims_is_07500() -> None:
    """SPEC: 15 supported of 20 claims persists ``faithfulness = 0.7500``."""
    value = faithfulness([FaithfulnessEntry(claims=20, supported=15)])

    assert value == 0.75
    assert format_metric(value) == "0.7500"


def test_worked_example_sums_across_entries() -> None:
    entries = [FaithfulnessEntry(claims=10, supported=8), FaithfulnessEntry(claims=10, supported=7)]

    assert faithfulness(entries) == 0.75


def test_a_single_supported_claim_scores_one() -> None:
    assert entry_faithfulness(1, 1) == 1.0
    assert faithfulness([FaithfulnessEntry(claims=1, supported=1)]) == 1.0


def test_zero_claims_scores_zero_rather_than_dividing_by_zero() -> None:
    assert entry_faithfulness(0, 0) == 0.0
    assert faithfulness([FaithfulnessEntry(claims=0, supported=0)]) == 0.0


def test_a_run_with_no_entries_has_no_claims_and_scores_zero() -> None:
    assert faithfulness([]) == 0.0


# --- arithmetic and rounding ----------------------------------------------


def test_aggregate_divides_total_supported_by_total_claims() -> None:
    entries = [FaithfulnessEntry(claims=2, supported=1), FaithfulnessEntry(claims=1, supported=1)]

    value = faithfulness(entries)

    assert value == 0.6667
    assert value == round_half_up(2 / 3)
    assert format_metric(value) == "0.6667"


def test_aggregate_rounds_half_up_not_to_even() -> None:
    # 1/32 = 0.03125 is exactly representable: Python's round gives 0.0312,
    # SPEC's half-up rule carries to 0.0313.
    value = faithfulness([FaithfulnessEntry(claims=32, supported=1)])

    assert round(1 / 32, 4) == 0.0312
    assert value == 0.0313


def test_entry_faithfulness_is_rounded_to_four_places() -> None:
    assert entry_faithfulness(3, 2) == 0.6667
    assert format_metric(entry_faithfulness(3, 2)) == "0.6667"


def test_entry_dataclass_exposes_its_rounded_faithfulness() -> None:
    assert FaithfulnessEntry(claims=3, supported=2).faithfulness == 0.6667
    assert FaithfulnessEntry(claims=0, supported=0).faithfulness == 0.0


# --- invalid counts --------------------------------------------------------


def test_supported_claims_cannot_exceed_total_claims() -> None:
    with pytest.raises(ValueError, match="supported"):
        FaithfulnessEntry(claims=1, supported=2)


def test_negative_claim_counts_are_rejected() -> None:
    with pytest.raises(ValueError, match="claims"):
        FaithfulnessEntry(claims=-1, supported=0)
    with pytest.raises(ValueError, match="supported"):
        FaithfulnessEntry(claims=1, supported=-1)


def test_non_integer_counts_are_rejected() -> None:
    with pytest.raises(TypeError, match="claims"):
        FaithfulnessEntry(claims=1.0, supported=1)  # type: ignore[arg-type]


# --- scoring bridge --------------------------------------------------------


def test_score_claims_returns_one_binary_verdict_per_claim() -> None:
    scorer = FakeEntailmentScorer([True, False])

    assert score_claims(["A claim.", "Another claim."], "context", scorer) == (True, False)


def test_score_answer_counts_claims_and_supported_claims() -> None:
    scorer = FakeEntailmentScorer([True, False])

    result = score_answer(
        "Late filings incur a penalty. Interest accrues daily.",
        citations=[],
        retrieved=chunks(),
        scorer=scorer,
    )

    assert result.claims == 2
    assert result.supported == 1
    assert result.faithfulness == 0.5


def test_score_answer_uses_only_cited_pages_as_context() -> None:
    scorer = FakeEntailmentScorer(default=True)

    result = score_answer(
        "Late filings incur a penalty. Interest accrues daily.",
        citations=[Citation(page=4, quote="Late filings incur a penalty.")],
        retrieved=chunks(),
        scorer=scorer,
    )

    assert result.claims == 2
    contexts = [context for _, context in scorer.calls]
    assert len(contexts) == 2
    assert all("Late filings" in context for context in contexts)
    assert all("Interest accrues" not in context for context in contexts)


def test_score_answer_uses_all_retrieved_chunks_when_nothing_is_cited() -> None:
    scorer = FakeEntailmentScorer(default=True)

    score_answer(
        "Late filings incur a penalty.",
        citations=[],
        retrieved=chunks(),
        scorer=scorer,
    )

    context = scorer.calls[0][1]
    assert "Late filings" in context
    assert "Interest accrues" in context


def test_a_zero_claim_answer_scores_zero_without_calling_the_scorer() -> None:
    scorer = FakeEntailmentScorer(default=True)

    result = score_answer("   \n\t ", citations=[], retrieved=chunks(), scorer=scorer)

    assert (result.claims, result.supported) == (0, 0)
    assert result.faithfulness == 0.0
    assert scorer.calls == []


def test_score_answer_accepts_a_minimal_protocol_implementation() -> None:
    class StubScorer:
        id = "stub"
        version = "1"

        def supports(self, claim: str, context: str) -> bool:
            return "supported" in claim

    result = score_answer(
        "This is supported. This is not.",
        citations=[],
        retrieved=chunks(),
        scorer=StubScorer(),
    )

    assert (result.claims, result.supported) == (2, 1)
