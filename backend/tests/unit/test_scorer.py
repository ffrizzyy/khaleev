"""Unit tests for the entailment scorer and context selection (T15, AC7).

The real scorer is a local sentence-transformers cross-encoder, but no test may
load a model or reach the network (SPEC AC8, Locked intent #12). So the model is
exercised through an injected fake cross-encoder, the no-model path through a
factory that raises, and the metric path through ``FakeEntailmentScorer`` with
constructed verdicts. Laziness is asserted directly: constructing the local
scorer must not call its model factory.
"""

from __future__ import annotations

from typing import Any

from khaleev.api.schemas import Citation
from khaleev.evals.scorer import (
    DEFAULT_NLI_MODEL,
    LEXICAL_SCORER_ID,
    NLI_SCORER_ID,
    SCORER_VERSION,
    EntailmentScorer,
    FakeEntailmentScorer,
    LexicalOverlapScorer,
    LocalEntailmentScorer,
    evidence_chunks,
    select_context,
)
from khaleev.retrieval.search import RetrievedChunk


def retrieved_chunks() -> tuple[RetrievedChunk, ...]:
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


# --- FakeEntailmentScorer --------------------------------------------------


def test_fake_scores_from_constructed_verdicts() -> None:
    scorer = FakeEntailmentScorer({"A claim.": True, "Another claim.": False})

    assert scorer.supports("A claim.", "any context") is True
    assert scorer.supports("Another claim.", "any context") is False
    assert scorer.id == "fake-entailment"
    assert scorer.version == "test"


def test_fake_uses_the_default_for_unmapped_claims() -> None:
    assert FakeEntailmentScorer(default=True).supports("Anything", "") is True
    assert FakeEntailmentScorer(default=False).supports("Anything", "") is False


def test_fake_consumes_a_verdict_sequence_in_order() -> None:
    scorer = FakeEntailmentScorer([True, False])

    assert scorer.supports("one", "") is True
    assert scorer.supports("two", "") is False
    assert scorer.supports("three", "") is False  # the last verdict repeats


def test_fake_records_every_claim_and_context() -> None:
    scorer = FakeEntailmentScorer()

    scorer.supports("claim", "context")

    assert scorer.calls == [("claim", "context")]


def test_fake_satisfies_the_entailment_protocol() -> None:
    assert isinstance(FakeEntailmentScorer(), EntailmentScorer)


# --- LexicalOverlapScorer (the deterministic fallback) --------------------


def test_lexical_supports_a_claim_covered_by_the_context() -> None:
    scorer = LexicalOverlapScorer()
    context = "Late filings incur a flat 200 credit penalty per return."

    assert scorer.supports("Late filings incur a flat 200 credit penalty", context) is True


def test_lexical_rejects_an_unrelated_claim() -> None:
    context = "Late filings incur a flat 200 credit penalty per return."

    assert LexicalOverlapScorer().supports("Interest accrues daily", context) is False


def test_lexical_requires_matching_numbers() -> None:
    context = "Late filings incur a flat 200 credit penalty per return."

    assert (
        LexicalOverlapScorer().supports("Late filings incur a flat 500 credit penalty", context)
        is False
    )


def test_lexical_rejects_a_claim_with_too_little_overlap() -> None:
    context = "Late filings incur a penalty."

    assert LexicalOverlapScorer().supports(
        "Late filings incur an extraordinary additional surcharge", context
    ) is False


def test_lexical_rejects_an_empty_claim_or_context() -> None:
    scorer = LexicalOverlapScorer()

    assert scorer.supports("", "Late filings incur a penalty.") is False
    assert scorer.supports("Late filings incur a penalty.", "") is False
    assert scorer.supports("...", "Late filings incur a penalty.") is False


def test_lexical_is_deterministic_and_reports_its_identity() -> None:
    scorer = LexicalOverlapScorer()
    context = "Late filings incur a flat 200 credit penalty per return."

    assert scorer.supports("Late filings incur a penalty", context) == scorer.supports(
        "Late filings incur a penalty", context
    )
    assert scorer.id == LEXICAL_SCORER_ID
    assert scorer.version == SCORER_VERSION


def test_lexical_satisfies_the_entailment_protocol() -> None:
    assert isinstance(LexicalOverlapScorer(), EntailmentScorer)


# --- context selection -----------------------------------------------------


def test_context_uses_only_cited_pages_when_the_answer_cites_pages() -> None:
    citations = [Citation(page=4, quote="Late filings incur a penalty.")]
    chunks = retrieved_chunks()

    selected = evidence_chunks(citations, chunks)
    context = select_context(citations, chunks)

    assert [chunk.page_number for chunk in selected] == [4]
    assert "Late filings" in context
    assert "Interest accrues" not in context


def test_context_uses_all_retrieved_chunks_when_nothing_is_cited() -> None:
    chunks = retrieved_chunks()

    selected = evidence_chunks([], chunks)
    context = select_context([], chunks)

    assert [chunk.page_number for chunk in selected] == [4, 9]
    assert "Late filings" in context
    assert "Interest accrues" in context


def test_an_unretrieved_cited_page_falls_back_to_all_chunks() -> None:
    citations = [Citation(page=7, quote="a page that was not retrieved")]
    chunks = retrieved_chunks()

    selected = evidence_chunks(citations, chunks)

    assert [chunk.page_number for chunk in selected] == [4, 9]


def test_context_without_chunks_is_empty() -> None:
    assert select_context([], ()) == ""


# --- LocalEntailmentScorer: laziness, real-model seam, fallback -----------


class _FakeConfig:
    """The piece of the cross-encoder config that picks the entailment label."""

    def __init__(self, id2label: dict[int, str]) -> None:
        self.id2label = id2label


class _FakeCrossEncoder:
    """A deterministic stand-in for a sentence-transformers cross-encoder."""

    def __init__(
        self,
        id2label: dict[int, str] | None = None,
        *,
        match_scores: tuple[float, float, float] = (0.0, 5.0, 0.0),
        miss_scores: tuple[float, float, float] = (5.0, 0.0, 0.0),
    ) -> None:
        self.config = _FakeConfig(
            id2label
            if id2label is not None
            else {0: "contradiction", 1: "entailment", 2: "neutral"}
        )
        self.match_scores = list(match_scores)
        self.miss_scores = list(miss_scores)
        self.calls: list[list[tuple[str, str]]] = []

    def predict(self, pairs: Any) -> list[list[float]]:
        batch = list(pairs)
        self.calls.append(batch)
        scores: list[list[float]] = []
        for premise, hypothesis in batch:
            if str(hypothesis).lower() in str(premise).lower():
                scores.append(list(self.match_scores))
            else:
                scores.append(list(self.miss_scores))
        return scores


class _BrokenCrossEncoder:
    """A model that loads but fails at prediction time."""

    config = _FakeConfig({0: "contradiction", 1: "entailment", 2: "neutral"})

    def predict(self, pairs: Any) -> list[list[float]]:
        raise RuntimeError("model exploded")


def test_the_local_scorer_is_lazy_and_reports_the_intended_model() -> None:
    loads: list[bool] = []

    scorer = LocalEntailmentScorer(
        "cross-encoder/test-nli",
        model_factory=lambda: loads.append(True) or _FakeCrossEncoder(),
    )

    assert loads == []
    assert scorer.backend == "unresolved"
    assert scorer.id == f"{NLI_SCORER_ID}:cross-encoder/test-nli"


def test_the_default_local_scorer_uses_the_spec_suggested_model() -> None:
    assert DEFAULT_NLI_MODEL == "cross-encoder/nli-deberta-v3-small"
    assert LocalEntailmentScorer().id == f"{NLI_SCORER_ID}:{DEFAULT_NLI_MODEL}"


def test_the_local_scorer_uses_an_injected_entailment_model() -> None:
    model = _FakeCrossEncoder()
    scorer = LocalEntailmentScorer("cross-encoder/test-nli", model_factory=lambda: model)

    assert (
        scorer.supports(
            "Late filings incur a penalty",
            "Late filings incur a penalty.",
        )
        is True
    )
    assert scorer.supports("Interest accrues daily", "Late filings incur a penalty.") is False
    assert scorer.backend == "nli"
    assert scorer.id == f"{NLI_SCORER_ID}:cross-encoder/test-nli"
    assert scorer.version == SCORER_VERSION
    # CrossEncoder takes (premise, hypothesis): the context is the premise.
    assert model.calls[0] == [("Late filings incur a penalty.", "Late filings incur a penalty")]


def test_the_entailment_label_is_read_from_the_model_config() -> None:
    model = _FakeCrossEncoder(
        id2label={0: "ENTAILMENT", 1: "neutral", 2: "contradiction"},
        match_scores=(5.0, 0.0, 0.0),
    )
    scorer = LocalEntailmentScorer("cross-encoder/test-nli", model_factory=lambda: model)

    # Logits put all weight on index 0, which is entailment for this model.
    assert scorer.supports("a claim", "a claim in context") is True


def test_the_local_scorer_falls_back_when_the_model_cannot_load() -> None:
    def unavailable() -> Any:
        raise ImportError("sentence-transformers is not installed")

    scorer = LocalEntailmentScorer("cross-encoder/test-nli", model_factory=unavailable)

    assert (
        scorer.supports(
            "Late filings incur a penalty", "Late filings incur a penalty."
        )
        is True
    )
    # Once the fallback runs, the scorer reports the identity that actually scored.
    assert scorer.id == LEXICAL_SCORER_ID


def test_the_local_scorer_falls_back_when_prediction_fails() -> None:
    scorer = LocalEntailmentScorer(
        "cross-encoder/test-nli", model_factory=lambda: _BrokenCrossEncoder()
    )

    assert (
        scorer.supports(
            "Late filings incur a penalty", "Late filings incur a penalty."
        )
        is True
    )
    assert scorer.supports("Interest accrues daily", "Late filings incur a penalty.") is False


def test_the_local_scorer_satisfies_the_entailment_protocol() -> None:
    scorer = LocalEntailmentScorer(
        "cross-encoder/test-nli", model_factory=lambda: _FakeCrossEncoder()
    )

    assert isinstance(scorer, EntailmentScorer)


def test_the_local_scorer_does_not_download_a_model_at_construction() -> None:
    # Constructing the default scorer must not import torch or touch the cache;
    # no assertion here about installation, only that nothing is eager.
    scorer = LocalEntailmentScorer()

    assert scorer.backend == "unresolved"
    assert isinstance(scorer.id, str)
    assert scorer.version == SCORER_VERSION
