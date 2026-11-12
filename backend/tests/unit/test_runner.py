"""Unit tests for the eval runner (T16, F5, AC5, AC10).

``evaluate`` walks a document's golden set: for every entry it retrieves the
top-k chunks, generates a cited answer, splits the answer into claims and scores
them, then returns one report with both aggregate metrics and per-entry results.
It writes nothing itself — the transaction boundary lives in
``khaleev.services.evals.run_eval`` and is exercised in
``tests/integration/test_eval_persistence.py``.

Every model-backed dependency is faked (``FakeEmbedder``, ``FakeGenerator``,
``FakeEntailmentScorer``); the only real scorer used is the local one with a
model factory that raises, so no model is loaded and no socket is opened
(SPEC AC8, Locked intent #12).

The golden set is deliberately built so both branches of the hit rule are
covered without depending on ranking luck: ``k`` is larger than the document's
page count, so every page is retrieved, one entry expects a page that exists
(hit) and one expects page 99, which cannot be retrieved (miss). Three entries
with two hits is 2/3, whose half-up value is ``0.6667`` — exactly the rounding
rule SPEC demands.
"""

from __future__ import annotations

from typing import Any

import pytest
from fixtures.pdf_factory import build_pdf
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from khaleev.config import Settings
from khaleev.evals.golden import GoldenSet, write_golden_file
from khaleev.evals.metrics.hit_rate import MetricUndefinedError
from khaleev.evals.runner import EvalReport, evaluate
from khaleev.evals.scorer import (
    DEFAULT_NLI_MODEL,
    LEXICAL_SCORER_ID,
    NLI_SCORER_ID,
    SCORER_VERSION,
    FakeEntailmentScorer,
    LocalEntailmentScorer,
)
from khaleev.generation import FakeGenerator, GenerationError
from khaleev.ingest.embedding import FakeEmbedder
from khaleev.models import EvalRun
from khaleev.services.documents import DocumentNotFoundError, upload_document

#: Larger than the document's page count, so every page is retrieved for every
#: entry and the hit/miss outcome is decided by the expected pages alone.
K = 10

PAGES = [
    "Refunds are processed within ten business days.",
    "Appeals must be filed within thirty days of the notice.",
    "Late filings incur a 200 credit penalty per return.",
    "The archive is closed on public holidays.",
]

#: [3] and [1] exist in the document (hit); [99] cannot be retrieved (miss).
GOLDEN_ENTRIES = [
    {
        "question": "What penalty applies to late filings?",
        "expected_answer": "Late filings incur a flat 200 credit penalty per return.",
        "expected_pages": [3],
    },
    {
        "question": "How long do refunds take to process?",
        "expected_answer": "Refunds are processed within ten business days.",
        "expected_pages": [1],
    },
    {
        "question": "What is the deadline for filing an appeal?",
        "expected_answer": "Appeals must be filed within thirty days of the notice.",
        "expected_pages": [99],
    },
]

#: One, two and one claim respectively: four claims in total.
ANSWERS = [
    "Late filings incur a penalty.",
    "Refunds take ten days. Appeals are due.",
    "The archive is closed.",
]

#: Two of the four claims are supported, so run faithfulness is 2/4 = 0.5.
VERDICTS = {
    "Late filings incur a penalty.": True,
    "Refunds take ten days.": False,
    "Appeals are due.": True,
    "The archive is closed.": False,
}


class _FailingGenerator:
    """A generator whose backend fails on the N-th call."""

    def __init__(self, fail_on: int = 2) -> None:
        self.fail_on = fail_on
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        if self.calls == self.fail_on:
            raise GenerationError("could not reach Ollama: connection refused")
        return "Late filings incur a penalty."


def _unavailable_model() -> Any:
    """A model factory that always fails, so the scorer falls back to lexical."""
    raise RuntimeError("the NLI model is not in the local cache")


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def generator() -> FakeGenerator:
    return FakeGenerator(ANSWERS)


@pytest.fixture
def scorer() -> FakeEntailmentScorer:
    return FakeEntailmentScorer(VERDICTS)


def _upload(session: Session, settings: Settings, embedder: FakeEmbedder) -> int:
    result = upload_document(
        session,
        pdf_bytes=build_pdf(PAGES),
        filename="tax-guide.pdf",
        data_dir=settings.data_dir,
        settings=settings,
        embedder=embedder,
    )
    return int(result.document.id)


def _document_with_golden(
    session: Session,
    settings: Settings,
    embedder: FakeEmbedder,
    entries: list[dict[str, Any]] | None = None,
) -> tuple[int, GoldenSet]:
    document_id = _upload(session, settings, embedder)
    golden_set = write_golden_file(
        settings.data_dir,
        document_id,
        GOLDEN_ENTRIES if entries is None else entries,
    )
    return document_id, golden_set


def _evaluate(
    session: Session,
    settings: Settings,
    document_id: int,
    embedder: FakeEmbedder,
    generator: Any,
    scorer: Any,
) -> EvalReport:
    return evaluate(
        document_id,
        session=session,
        k=K,
        embedder=embedder,
        generator=generator,
        scorer=scorer,
        settings=settings,
        data_dir=settings.data_dir,
    )


def _run_count(session: Session) -> int:
    value = session.scalar(select(func.count()).select_from(EvalRun))
    return int(value or 0)


# --- per-entry results ----------------------------------------------------


def test_evaluate_scores_every_golden_entry_in_file_order(
    migrated_session: Session,
    settings: Settings,
    embedder: FakeEmbedder,
    generator: FakeGenerator,
    scorer: FakeEntailmentScorer,
) -> None:
    document_id, _ = _document_with_golden(migrated_session, settings, embedder)

    report = _evaluate(migrated_session, settings, document_id, embedder, generator, scorer)

    assert [result.golden_index for result in report.entries] == [0, 1, 2]
    assert [result.question for result in report.entries] == [
        entry["question"] for entry in GOLDEN_ENTRIES
    ]


def test_a_hit_is_page_level_and_an_unretrievable_page_is_a_miss(
    migrated_session: Session,
    settings: Settings,
    embedder: FakeEmbedder,
    generator: FakeGenerator,
    scorer: FakeEntailmentScorer,
) -> None:
    document_id, _ = _document_with_golden(migrated_session, settings, embedder)

    report = _evaluate(migrated_session, settings, document_id, embedder, generator, scorer)

    assert [result.hit for result in report.entries] == [True, True, False]


def test_entry_results_carry_the_answer_claim_counts_and_entry_faithfulness(
    migrated_session: Session,
    settings: Settings,
    embedder: FakeEmbedder,
    generator: FakeGenerator,
    scorer: FakeEntailmentScorer,
) -> None:
    document_id, _ = _document_with_golden(migrated_session, settings, embedder)

    report = _evaluate(migrated_session, settings, document_id, embedder, generator, scorer)

    assert [result.answer for result in report.entries] == ANSWERS
    assert [result.claims for result in report.entries] == [1, 2, 1]
    assert [result.supported_claims for result in report.entries] == [1, 1, 0]
    assert [result.faithfulness for result in report.entries] == [1.0, 0.5, 0.0]


# --- aggregate metrics ----------------------------------------------------


def test_the_aggregate_metrics_are_half_up_rounded_and_within_range(
    migrated_session: Session,
    settings: Settings,
    embedder: FakeEmbedder,
    generator: FakeGenerator,
    scorer: FakeEntailmentScorer,
) -> None:
    document_id, _ = _document_with_golden(migrated_session, settings, embedder)

    report = _evaluate(migrated_session, settings, document_id, embedder, generator, scorer)

    # 2 hits of 3 entries is 0.6666...; half-up to four places is 0.6667.
    assert report.hit_rate == 0.6667
    # 2 supported claims of 4 is 0.5.
    assert report.faithfulness == 0.5
    assert 0.0 <= report.hit_rate <= 1.0
    assert 0.0 <= report.faithfulness <= 1.0


# --- config ---------------------------------------------------------------


def test_the_config_records_every_comparison_field(
    migrated_session: Session,
    settings: Settings,
    embedder: FakeEmbedder,
    generator: FakeGenerator,
    scorer: FakeEntailmentScorer,
) -> None:
    document_id, golden_set = _document_with_golden(migrated_session, settings, embedder)

    report = _evaluate(migrated_session, settings, document_id, embedder, generator, scorer)

    assert report.k == K
    assert report.embedder_id == settings.embedder_id
    assert report.scorer_id == FakeEntailmentScorer.id
    assert report.scorer_version == FakeEntailmentScorer.version
    assert report.golden_set_revision == golden_set.revision
    assert report.config == {
        "document_id": document_id,
        "k": K,
        "embedder_id": settings.embedder_id,
        "generator": {"kind": "FakeGenerator", "model": None},
        "scorer_id": FakeEntailmentScorer.id,
        "scorer_version": FakeEntailmentScorer.version,
        "golden_set_revision": golden_set.revision,
    }


def test_the_scorer_id_is_read_after_scoring_so_a_fallback_is_recorded(
    migrated_session: Session,
    settings: Settings,
    embedder: FakeEmbedder,
    generator: FakeGenerator,
) -> None:
    document_id, _ = _document_with_golden(migrated_session, settings, embedder)
    scorer = LocalEntailmentScorer(model_factory=_unavailable_model)
    # Before the first claim the scorer still advertises the intended NLI identity.
    assert scorer.id == f"{NLI_SCORER_ID}:{DEFAULT_NLI_MODEL}"

    report = _evaluate(migrated_session, settings, document_id, embedder, generator, scorer)

    assert report.scorer_id == LEXICAL_SCORER_ID
    assert report.scorer_id != f"{NLI_SCORER_ID}:{DEFAULT_NLI_MODEL}"
    assert report.config["scorer_id"] == LEXICAL_SCORER_ID
    assert report.config["scorer_version"] == SCORER_VERSION


# --- orchestration --------------------------------------------------------


def test_the_generator_is_called_once_per_entry_with_its_question(
    migrated_session: Session,
    settings: Settings,
    embedder: FakeEmbedder,
    generator: FakeGenerator,
    scorer: FakeEntailmentScorer,
) -> None:
    document_id, _ = _document_with_golden(migrated_session, settings, embedder)

    _evaluate(migrated_session, settings, document_id, embedder, generator, scorer)

    assert len(generator.prompts) == len(GOLDEN_ENTRIES)
    for prompt, entry in zip(generator.prompts, GOLDEN_ENTRIES, strict=True):
        assert entry["question"] in prompt


def test_evaluate_writes_nothing_itself(
    migrated_session: Session,
    settings: Settings,
    embedder: FakeEmbedder,
    generator: FakeGenerator,
    scorer: FakeEntailmentScorer,
) -> None:
    document_id, _ = _document_with_golden(migrated_session, settings, embedder)

    _evaluate(migrated_session, settings, document_id, embedder, generator, scorer)

    assert _run_count(migrated_session) == 0


# --- rejection and failure paths -----------------------------------------


def test_an_empty_golden_set_raises_the_metric_undefined_error(
    migrated_session: Session,
    settings: Settings,
    embedder: FakeEmbedder,
    generator: FakeGenerator,
    scorer: FakeEntailmentScorer,
) -> None:
    # Uploading seeds an empty golden file; nothing fills it in.
    document_id = _upload(migrated_session, settings, embedder)

    with pytest.raises(MetricUndefinedError) as excinfo:
        _evaluate(migrated_session, settings, document_id, embedder, generator, scorer)

    assert "empty" in str(excinfo.value)
    assert generator.prompts == []
    assert _run_count(migrated_session) == 0


def test_a_generator_failure_stops_the_run(
    migrated_session: Session,
    settings: Settings,
    embedder: FakeEmbedder,
    scorer: FakeEntailmentScorer,
) -> None:
    document_id, _ = _document_with_golden(migrated_session, settings, embedder)
    failing = _FailingGenerator(fail_on=2)

    with pytest.raises(GenerationError):
        _evaluate(migrated_session, settings, document_id, embedder, failing, scorer)

    # Fail fast: the first entry was answered, the second failed, no third call.
    assert failing.calls == 2
    assert _run_count(migrated_session) == 0


def test_an_unknown_document_is_reported_before_any_work(
    migrated_session: Session,
    settings: Settings,
    embedder: FakeEmbedder,
    generator: FakeGenerator,
    scorer: FakeEntailmentScorer,
) -> None:
    with pytest.raises(DocumentNotFoundError):
        _evaluate(migrated_session, settings, 424_242, embedder, generator, scorer)

    assert generator.prompts == []
