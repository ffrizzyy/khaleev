"""Integration tests for eval-run persistence (T16, F5, AC5, AC10).

``khaleev.services.evals.run_eval`` is the transaction boundary: it scores the
document's golden set with injected fakes and then writes exactly one
``eval_runs`` row and one ``eval_run_entries`` row per golden entry, in one
commit. These tests read the rows back from the migrated temp database — not
from the report — because the point of T16 is that an eval run is durable and
honest about what produced it.

Error policy (documented on the service): **fail fast**. If the golden set is
empty or any entry cannot be generated or scored, the run raises and nothing is
persisted. A half-scored run would either be missing entries or have a different
denominator than the run it is compared with, which is exactly the dishonesty the
eval layer exists to prevent.

Both runs of the same document/config test that history is the product: the same
eval repeated twice must produce two retrievable rows, not overwrite the first.
"""

from __future__ import annotations

from typing import Any

import pytest
from fixtures.pdf_factory import build_pdf
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from khaleev.config import Settings
from khaleev.db import create_session_factory
from khaleev.evals.golden import GoldenSet, write_golden_file
from khaleev.evals.metrics.hit_rate import MetricUndefinedError
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
from khaleev.models import EvalRun, EvalRunEntry
from khaleev.services.documents import upload_document
from khaleev.services.evals import (
    EvalRunNotFoundError,
    get_eval_run,
    list_eval_runs,
    run_eval,
)

K = 10

PAGES = [
    "Refunds are processed within ten business days.",
    "Appeals must be filed within thirty days of the notice.",
    "Late filings incur a 200 credit penalty per return.",
    "The archive is closed on public holidays.",
]

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

ANSWERS = [
    "Late filings incur a penalty.",
    "Refunds take ten days. Appeals are due.",
    "The archive is closed.",
]

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
) -> tuple[int, GoldenSet]:
    document_id = _upload(session, settings, embedder)
    golden_set = write_golden_file(settings.data_dir, document_id, GOLDEN_ENTRIES)
    return document_id, golden_set


def _run(
    session: Session,
    settings: Settings,
    document_id: int,
    embedder: FakeEmbedder,
    generator: Any,
    scorer: Any,
) -> EvalRun:
    return run_eval(
        session,
        document_id,
        k=K,
        embedder=embedder,
        generator=generator,
        scorer=scorer,
        settings=settings,
        data_dir=settings.data_dir,
    )


def _counts(session: Session) -> tuple[int, int]:
    runs = session.scalar(select(func.count()).select_from(EvalRun)) or 0
    entries = session.scalar(select(func.count()).select_from(EvalRunEntry)) or 0
    return int(runs), int(entries)


# --- the happy path -------------------------------------------------------


def test_a_run_persists_one_row_and_one_entry_per_golden_entry(
    migrated_session: Session,
    settings: Settings,
    embedder: FakeEmbedder,
    generator: FakeGenerator,
    scorer: FakeEntailmentScorer,
) -> None:
    document_id, _ = _document_with_golden(migrated_session, settings, embedder)

    run = _run(migrated_session, settings, document_id, embedder, generator, scorer)

    assert _counts(migrated_session) == (1, len(GOLDEN_ENTRIES))
    migrated_session.expire_all()
    stored = get_eval_run(migrated_session, run.id)
    assert stored.document_id == document_id
    assert stored.k == K
    assert stored.created_at is not None
    assert stored.hit_rate == 0.6667
    assert stored.faithfulness == 0.5
    assert 0.0 <= stored.hit_rate <= 1.0
    assert 0.0 <= stored.faithfulness <= 1.0
    assert [entry.golden_index for entry in stored.entries] == [0, 1, 2]


def test_each_entry_row_records_the_scored_result(
    migrated_session: Session,
    settings: Settings,
    embedder: FakeEmbedder,
    generator: FakeGenerator,
    scorer: FakeEntailmentScorer,
) -> None:
    document_id, _ = _document_with_golden(migrated_session, settings, embedder)

    run = _run(migrated_session, settings, document_id, embedder, generator, scorer)

    migrated_session.expire_all()
    entries = list(get_eval_run(migrated_session, run.id).entries)
    assert [entry.hit for entry in entries] == [True, True, False]
    assert [entry.answer for entry in entries] == ANSWERS
    assert [entry.claims for entry in entries] == [1, 2, 1]
    assert [entry.supported_claims for entry in entries] == [1, 1, 0]
    assert [entry.faithfulness for entry in entries] == [1.0, 0.5, 0.0]


def test_the_run_row_records_the_model_identities_and_the_full_config(
    migrated_session: Session,
    settings: Settings,
    embedder: FakeEmbedder,
    generator: FakeGenerator,
    scorer: FakeEntailmentScorer,
) -> None:
    document_id, golden_set = _document_with_golden(migrated_session, settings, embedder)

    run = _run(migrated_session, settings, document_id, embedder, generator, scorer)

    migrated_session.expire_all()
    stored = get_eval_run(migrated_session, run.id)
    assert stored.embedder_id == settings.embedder_id
    assert stored.scorer_id == FakeEntailmentScorer.id
    config = stored.config
    assert config["document_id"] == document_id
    assert config["k"] == K
    assert config["embedder_id"] == settings.embedder_id
    assert config["generator"]["kind"] == "FakeGenerator"
    assert config["scorer_id"] == FakeEntailmentScorer.id
    assert config["scorer_version"] == FakeEntailmentScorer.version
    assert config["golden_set_revision"] == golden_set.revision


def test_a_fallback_run_persists_the_fallback_scorer_id_not_the_nli_id(
    migrated_session: Session,
    settings: Settings,
    embedder: FakeEmbedder,
    generator: FakeGenerator,
) -> None:
    document_id, _ = _document_with_golden(migrated_session, settings, embedder)
    scorer = LocalEntailmentScorer(model_factory=_unavailable_model)
    assert scorer.id == f"{NLI_SCORER_ID}:{DEFAULT_NLI_MODEL}"

    run = _run(migrated_session, settings, document_id, embedder, generator, scorer)

    migrated_session.expire_all()
    stored = get_eval_run(migrated_session, run.id)
    assert stored.scorer_id == LEXICAL_SCORER_ID
    assert stored.scorer_id != f"{NLI_SCORER_ID}:{DEFAULT_NLI_MODEL}"
    assert stored.config["scorer_id"] == LEXICAL_SCORER_ID
    assert stored.config["scorer_version"] == SCORER_VERSION


# --- rejection and failure paths -----------------------------------------


def test_an_empty_golden_set_is_rejected_and_persists_nothing(
    migrated_session: Session,
    settings: Settings,
    embedder: FakeEmbedder,
    generator: FakeGenerator,
    scorer: FakeEntailmentScorer,
) -> None:
    # Uploading seeds an empty golden file; nothing fills it in.
    document_id = _upload(migrated_session, settings, embedder)

    with pytest.raises(MetricUndefinedError):
        _run(migrated_session, settings, document_id, embedder, generator, scorer)

    assert _counts(migrated_session) == (0, 0)
    assert generator.prompts == []


def test_a_generator_failure_persists_no_partial_run_and_leaves_the_session_usable(
    migrated_session: Session,
    settings: Settings,
    embedder: FakeEmbedder,
    scorer: FakeEntailmentScorer,
) -> None:
    document_id, _ = _document_with_golden(migrated_session, settings, embedder)
    failing = _FailingGenerator(fail_on=2)

    with pytest.raises(GenerationError):
        _run(migrated_session, settings, document_id, embedder, failing, scorer)

    assert failing.calls == 2
    assert _counts(migrated_session) == (0, 0)

    # The rollback left the session clean: a later run succeeds normally.
    run = _run(
        migrated_session,
        settings,
        document_id,
        embedder,
        FakeGenerator(ANSWERS),
        scorer,
    )
    assert _counts(migrated_session) == (1, len(GOLDEN_ENTRIES))
    assert get_eval_run(migrated_session, run.id).hit_rate == 0.6667


# --- history --------------------------------------------------------------


def test_two_runs_with_the_same_config_are_both_persisted_and_retrievable(
    migrated_session: Session,
    migrated_engine: Engine,
    settings: Settings,
    embedder: FakeEmbedder,
    generator: FakeGenerator,
    scorer: FakeEntailmentScorer,
) -> None:
    document_id, _ = _document_with_golden(migrated_session, settings, embedder)

    # The same configuration twice. ``FakeGenerator`` consumes its script, so a
    # fresh instance per run replays the same answers — as the real model would.
    first = _run(migrated_session, settings, document_id, embedder, generator, scorer)
    second = _run(
        migrated_session,
        settings,
        document_id,
        embedder,
        FakeGenerator(ANSWERS),
        scorer,
    )

    assert first.id != second.id
    with create_session_factory(migrated_engine)() as reader:
        history = list_eval_runs(reader, document_id)
        assert [run.id for run in history] == [first.id, second.id]
        for run in history:
            assert run.hit_rate == first.hit_rate
            assert run.faithfulness == first.faithfulness
            assert len(list(run.entries)) == len(GOLDEN_ENTRIES)
        assert get_eval_run(reader, second.id).document_id == document_id


def test_an_unknown_run_id_is_reported(migrated_session: Session) -> None:
    with pytest.raises(EvalRunNotFoundError):
        get_eval_run(migrated_session, 424_242)
