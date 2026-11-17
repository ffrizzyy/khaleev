"""Unit tests for per-run served-model provenance (T30, Locked intent 19).

``CloudGenerator`` records which model actually answered on a **per-call**
attribute that is overwritten every time — never accumulated. The eval runner
snapshots that attribute immediately after each entry's ``generate()`` into a
list built *inside* ``evaluate()``, so a previous run's or an interactive ask's
model can never be attributed to the current run. The persisted
``config["generator"]`` gains ``served_models`` (distinct, first-seen order) only
when at least one model was reported; without one the key is absent, which is
what keeps every fake/Ollama run's config byte-identical.

Requests go through ``httpx.MockTransport``; the suite-wide socket guard proves
no connection is attempted (Locked intent #12, AC8). The document, golden set,
embedder and scorer are fakes, built here rather than borrowed from
``test_runner.py`` (a file this task may not edit).
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from fixtures.pdf_factory import build_pdf
from sqlalchemy.orm import Session

from khaleev.config import Settings
from khaleev.evals.comparability import SIGNATURE_FIELDS
from khaleev.evals.golden import GoldenSet, write_golden_file
from khaleev.evals.runner import EvalReport, evaluate
from khaleev.evals.scorer import FakeEntailmentScorer
from khaleev.generation import FakeGenerator, Generator
from khaleev.generation.cloud import CloudGenerator
from khaleev.ingest.embedding import FakeEmbedder
from khaleev.models import EvalRun
from khaleev.services.documents import upload_document
from khaleev.services.evals import run_eval

API_KEY = "test-key"
MODEL = "primary/model:free"
BASE_URL = "https://cloud.example.test/v1"
K = 10
ANSWER = "Refunds are processed within ten business days. [page 1]"
Handler = Callable[[httpx.Request], httpx.Response]

PAGES = [
    "Refunds are processed within ten business days.",
    "Appeals must be filed within thirty days of the notice.",
    "Late filings incur a 200 credit penalty per return.",
]

_MISSING = object()


def _client(handler: Handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _settings(**kwargs: object) -> Settings:
    values: dict[str, object] = {
        "generator": "cloud",
        "cloud_api_key": API_KEY,
        "cloud_model": MODEL,
        "cloud_provider": "openrouter",
    }
    values.update(kwargs)
    return Settings(_env_file=None, **values)


def _response_body(reported: object) -> dict[str, object]:
    """A chat-completions body, optionally carrying a ``model`` field."""
    body: dict[str, object] = {
        "choices": [{"message": {"role": "assistant", "content": ANSWER}}]
    }
    if reported is not _MISSING:
        body["model"] = reported
    return body


def _handler(reported: list[object]) -> Handler:
    """Serve ``reported`` in order; the last value repeats for extra calls."""
    queue = list(reported)

    def handle(request: httpx.Request) -> httpx.Response:
        value = queue.pop(0) if len(queue) > 1 else queue[0]
        return httpx.Response(200, json=_response_body(value))

    return handle


def _cloud_generator(reported: list[object], **kwargs: object) -> CloudGenerator:
    values: dict[str, object] = {
        "base_url": BASE_URL,
        "client": _client(_handler(reported)),
    }
    values.update(kwargs)
    return CloudGenerator(API_KEY, MODEL, **values)


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
    count: int = 2,
) -> tuple[int, GoldenSet]:
    document_id = _upload(session, settings, embedder)
    entries = [
        {
            "question": f"What does the guide say on page one (entry {index})?",
            "expected_answer": "Refunds are processed within ten business days.",
            "expected_pages": [1],
        }
        for index in range(count)
    ]
    golden_set = write_golden_file(settings.data_dir, document_id, entries)
    return document_id, golden_set


def _evaluate(
    session: Session,
    settings: Settings,
    document_id: int,
    generator: Generator,
) -> EvalReport:
    return evaluate(
        document_id,
        session=session,
        k=K,
        embedder=FakeEmbedder(),
        generator=generator,
        scorer=FakeEntailmentScorer(default=False),
        settings=settings,
        data_dir=settings.data_dir,
    )


# ---------------------------------------------------------------------------
# The client attribute: per call, overwritten, never accumulated
# ---------------------------------------------------------------------------


def test_the_served_model_starts_unset_and_is_read_from_the_response() -> None:
    generator = _cloud_generator(["b"])
    assert generator.last_served_model is None

    generator.generate("prompt")

    assert generator.last_served_model == "b"


def test_the_served_model_is_overwritten_on_every_call() -> None:
    generator = _cloud_generator(["a", "b"])

    generator.generate("first")
    assert generator.last_served_model == "a"

    generator.generate("second")
    assert generator.last_served_model == "b"


@pytest.mark.parametrize(
    "reported",
    [_MISSING, 17, "", "   ", None],
    ids=["absent", "non-string", "empty", "blank", "null"],
)
def test_an_unusable_model_contributes_nothing(reported: object) -> None:
    generator = _cloud_generator(["a", reported])

    generator.generate("first")
    assert generator.last_served_model == "a"

    generator.generate("second")
    assert generator.last_served_model is None


# ---------------------------------------------------------------------------
# The run-local snapshot and the persisted shape
# ---------------------------------------------------------------------------


def test_two_different_served_models_are_recorded_in_first_seen_order(
    migrated_session: Session,
) -> None:
    settings = _settings()
    embedder = FakeEmbedder()
    document_id, _ = _document_with_golden(migrated_session, settings, embedder, count=2)
    generator = _cloud_generator(["a", "b"])

    report = _evaluate(migrated_session, settings, document_id, generator)

    assert report.served_models == ("a", "b")
    identity = report.config["generator"]
    assert identity["kind"] == "cloud"
    assert identity["model"] == MODEL
    assert identity["served_models"] == ["a", "b"]


def test_a_repeated_served_model_is_recorded_once(migrated_session: Session) -> None:
    settings = _settings()
    embedder = FakeEmbedder()
    document_id, _ = _document_with_golden(migrated_session, settings, embedder, count=2)
    generator = _cloud_generator(["a", "a"])

    report = _evaluate(migrated_session, settings, document_id, generator)

    assert report.served_models == ("a",)
    assert report.config["generator"]["served_models"] == ["a"]


def test_a_model_outside_the_configured_list_is_recorded_verbatim(
    migrated_session: Session,
) -> None:
    """The list is a routing hint, not a whitelist."""
    settings = _settings(cloud_fallback_models="fallback/one:free")
    embedder = FakeEmbedder()
    document_id, _ = _document_with_golden(migrated_session, settings, embedder, count=1)
    generator = _cloud_generator(["router/picked-this"])

    report = _evaluate(migrated_session, settings, document_id, generator)

    assert report.config["generator"]["served_models"] == ["router/picked-this"]


@pytest.mark.parametrize(
    "reported",
    [_MISSING, 17, "", "   "],
    ids=["absent", "non-string", "empty", "blank"],
)
def test_no_reported_model_omits_the_key_entirely(
    migrated_session: Session, reported: object
) -> None:
    settings = _settings()
    embedder = FakeEmbedder()
    document_id, _ = _document_with_golden(migrated_session, settings, embedder, count=2)
    generator = _cloud_generator([reported])

    report = _evaluate(migrated_session, settings, document_id, generator)

    assert report.served_models == ()
    assert "served_models" not in report.config["generator"]
    assert report.config["generator"] == {"kind": "cloud", "model": MODEL}


def test_a_fake_generator_run_is_byte_identical_to_today(
    migrated_session: Session,
) -> None:
    settings = Settings(_env_file=None)
    embedder = FakeEmbedder()
    document_id, golden_set = _document_with_golden(
        migrated_session, settings, embedder, count=2
    )

    report = _evaluate(migrated_session, settings, document_id, FakeGenerator([ANSWER]))

    assert report.served_models == ()
    assert report.config == {
        "document_id": document_id,
        "k": K,
        "embedder_id": settings.embedder_id,
        "generator": {"kind": "FakeGenerator", "model": None},
        "scorer_id": FakeEntailmentScorer.id,
        "scorer_version": FakeEntailmentScorer.version,
        "golden_set_revision": golden_set.revision,
    }


def test_each_run_snapshots_only_its_own_calls(migrated_session: Session) -> None:
    """One long-lived generator shared by two runs: no cross-run leakage."""
    settings = _settings()
    embedder = FakeEmbedder()
    document_id, _ = _document_with_golden(migrated_session, settings, embedder, count=2)
    generator = _cloud_generator(["a", "a", "b", "b"])

    first = _evaluate(migrated_session, settings, document_id, generator)
    second = _evaluate(migrated_session, settings, document_id, generator)

    assert first.config["generator"]["served_models"] == ["a"]
    assert second.config["generator"]["served_models"] == ["b"]


def test_the_persisted_run_carries_served_models_and_the_signature_is_unchanged(
    migrated_session: Session,
) -> None:
    settings = _settings()
    embedder = FakeEmbedder()
    document_id, _ = _document_with_golden(migrated_session, settings, embedder, count=2)
    generator = _cloud_generator(["a", "b"])

    run = run_eval(
        migrated_session,
        document_id,
        k=K,
        embedder=embedder,
        generator=generator,
        scorer=FakeEntailmentScorer(default=False),
        settings=settings,
        data_dir=settings.data_dir,
    )

    persisted = migrated_session.get(EvalRun, run.id)
    assert persisted is not None
    identity = persisted.config["generator"]
    assert identity == {"kind": "cloud", "model": MODEL, "served_models": ["a", "b"]}
    # Provenance, not a comparability input: the four-field signature is untouched.
    assert SIGNATURE_FIELDS == ("golden_set_revision", "k", "embedder_id", "scorer_id")
