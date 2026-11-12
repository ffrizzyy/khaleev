"""Integration tests for the eval API (T17, F5, AC5, AC6, AC10).

The app is built by ``create_app`` with a fake embedder, generator and scorer, so
this exercises the real routes, the real service transaction and the real scorer
boundary without loading a model or opening a socket (SPEC AC8, Locked intent
#12). Uploading through the API means the document's chunks are actually
embedded, so retrieval returns real pages and hit rate is meaningful.

Comparability is read back through the history endpoint after two runs: the
same-config pair is not flagged, the different-``k`` pair is, and updating the
live settings afterwards does not change a flag — the flag is a function of the
persisted rows, not of process memory (AC10).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fixtures.api_client import ApiClient
from fixtures.pdf_factory import build_pdf
from sqlalchemy.engine import Engine

from khaleev.app import create_app
from khaleev.config import Settings
from khaleev.evals.golden import write_golden_file
from khaleev.evals.scorer import FakeEntailmentScorer
from khaleev.generation import FakeGenerator, GenerationError
from khaleev.ingest.embedding import FakeEmbedder

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

#: A single-answer generator that repeats, so several runs are identical.
REPEATING_ANSWER = "Late filings incur a penalty."


class _FailingGenerator:
    """A generator whose backend fails on the N-th call (Ollama is down)."""

    def __init__(self, fail_on: int = 2) -> None:
        self.fail_on = fail_on
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        if self.calls == self.fail_on:
            raise GenerationError(
                "could not reach Ollama at http://localhost:11434/api/generate: "
                "connection refused. Is Ollama running? Start it with `ollama serve` and retry."
            )
        return REPEATING_ANSWER


class _UnavailableScorer:
    """A scorer whose model cannot be loaded, to exercise the 503 mapping."""

    id = "unavailable-entailment"
    version = "test"

    def supports(self, claim: str, context: str) -> bool:
        raise RuntimeError("the entailment model is not installed")


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def scorer() -> FakeEntailmentScorer:
    return FakeEntailmentScorer(VERDICTS)


def _make_app(
    settings: Settings,
    embedder: FakeEmbedder,
    *,
    generator: Any | None = None,
    scorer: Any | None = None,
) -> FastAPI:
    return create_app(
        settings=settings,
        embedder=embedder,
        generator=generator if generator is not None else FakeGenerator(ANSWERS),
        scorer=scorer if scorer is not None else FakeEntailmentScorer(VERDICTS),
    )


@pytest.fixture
def app(
    migrated_engine: Engine,
    settings: Settings,
    embedder: FakeEmbedder,
    scorer: FakeEntailmentScorer,
) -> FastAPI:
    return _make_app(settings, embedder, generator=FakeGenerator(ANSWERS), scorer=scorer)


@pytest.fixture
def client(app: FastAPI) -> Iterator[ApiClient]:
    with ApiClient(app) as client:
        yield client


@pytest.fixture
def client_for(migrated_engine: Engine, settings: Settings, embedder: FakeEmbedder):
    """Build extra app clients with a different generator or scorer."""

    def build(*, generator: Any | None = None, scorer: Any | None = None) -> ApiClient:
        return ApiClient(_make_app(settings, embedder, generator=generator, scorer=scorer))

    return build


def _upload(client: ApiClient) -> int:
    response = client.post(
        "/api/documents",
        files={"file": ("tax-guide.pdf", build_pdf(PAGES), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _seed_golden(settings: Settings, document_id: int) -> Any:
    return write_golden_file(settings.data_dir, document_id, GOLDEN_ENTRIES)


def _start(client: ApiClient, document_id: int, k: int | None = None):
    payload: dict[str, Any] = {} if k is None else {"k": k}
    return client.post(f"/api/documents/{document_id}/evals", json=payload)


def _history(client: ApiClient, document_id: int):
    return client.get(f"/api/documents/{document_id}/evals")


# --- starting and reading a run -------------------------------------------


def test_start_returns_the_persisted_run_with_both_metrics(
    client: ApiClient, settings: Settings, scorer: FakeEntailmentScorer
) -> None:
    document_id = _upload(client)
    golden_set = _seed_golden(settings, document_id)

    response = _start(client, document_id, k=3)

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body["id"], int)
    assert body["document_id"] == document_id
    assert body["k"] == 3
    assert body["hit_rate"] == 0.6667
    assert body["faithfulness"] == 0.5
    assert 0.0 <= body["hit_rate"] <= 1.0
    assert 0.0 <= body["faithfulness"] <= 1.0
    assert body["embedder_id"] == "all-MiniLM-L6-v2"
    assert body["scorer_id"] == FakeEntailmentScorer.id
    assert body["config"]["golden_set_revision"] == golden_set.revision
    assert body["config"]["k"] == 3
    assert body["config"]["document_id"] == document_id
    # The injected scorer is the one that judged every claim.
    assert scorer.calls


def test_start_defaults_k_from_settings_when_no_body_is_sent(
    client: ApiClient, settings: Settings
) -> None:
    document_id = _upload(client)
    _seed_golden(settings, document_id)

    response = client.post(f"/api/documents/{document_id}/evals")

    assert response.status_code == 200, response.text
    assert settings.retrieval_k == 5
    assert response.json()["k"] == 5
    assert response.json()["config"]["k"] == 5


def test_start_rejects_a_non_positive_k(client: ApiClient, settings: Settings) -> None:
    document_id = _upload(client)
    _seed_golden(settings, document_id)

    assert _start(client, document_id, k=0).status_code == 422


def test_get_run_returns_the_aggregate_and_every_entry(
    client: ApiClient, settings: Settings
) -> None:
    document_id = _upload(client)
    _seed_golden(settings, document_id)
    started = _start(client, document_id).json()

    response = client.get(f"/api/evals/{started['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == started["id"]
    assert body["hit_rate"] == 0.6667
    assert body["faithfulness"] == 0.5
    entries = body["entries"]
    assert [entry["golden_index"] for entry in entries] == [0, 1, 2]
    assert [entry["hit"] for entry in entries] == [True, True, False]
    assert [entry["answer"] for entry in entries] == ANSWERS
    assert [entry["claims"] for entry in entries] == [1, 2, 1]
    assert [entry["supported_claims"] for entry in entries] == [1, 1, 0]
    assert [entry["faithfulness"] for entry in entries] == [1.0, 0.5, 0.0]


# --- history and comparability -------------------------------------------


def test_history_has_one_summary_per_run_newest_first(
    client_for, settings: Settings
) -> None:
    with client_for(generator=FakeGenerator(REPEATING_ANSWER)) as client:
        document_id = _upload(client)
        _seed_golden(settings, document_id)
        first = _start(client, document_id, k=5).json()
        second = _start(client, document_id, k=5).json()

        response = _history(client, document_id)

    assert response.status_code == 200
    body = response.json()
    assert [row["id"] for row in body] == [second["id"], first["id"]]
    for row in body:
        assert row["created_at"]
        assert row["k"] == 5
        assert row["hit_rate"] == 0.6667
        assert row["faithfulness"] == 1.0
        assert row["embedder_id"] == "all-MiniLM-L6-v2"
        assert row["scorer_id"] == FakeEntailmentScorer.id
        assert row["config"]["k"] == 5
        # Same config as the most recent run: comparable, not flagged.
        assert row["flagged"] is False
        assert row["comparable"] is True


def test_history_flags_a_run_made_with_a_different_k(client_for, settings: Settings) -> None:
    with client_for(generator=FakeGenerator(REPEATING_ANSWER)) as client:
        document_id = _upload(client)
        _seed_golden(settings, document_id)
        first = _start(client, document_id, k=5).json()
        second = _start(client, document_id, k=10).json()

        response = _history(client, document_id)

    body = response.json()
    assert [row["id"] for row in body] == [second["id"], first["id"]]
    assert [row["k"] for row in body] == [10, 5]
    assert [row["flagged"] for row in body] == [False, True]
    assert [row["comparable"] for row in body] == [True, False]


def test_flags_are_computed_from_persisted_config_not_live_settings(
    client_for, settings: Settings
) -> None:
    with client_for(generator=FakeGenerator(REPEATING_ANSWER)) as client:
        document_id = _upload(client)
        _seed_golden(settings, document_id)
        _start(client, document_id, k=5)
        _start(client, document_id, k=10)
        # Move the live setting back to 5; the persisted k's still disagree.
        assert client.put("/api/config", json={"k": 5}).status_code == 200

        body = _history(client, document_id).json()

    assert [row["flagged"] for row in body] == [False, True]


# --- domain errors --------------------------------------------------------


def test_start_on_an_unknown_document_is_404(client: ApiClient) -> None:
    assert _start(client, 424_242).status_code == 404


def test_history_of_an_unknown_document_is_404(client: ApiClient) -> None:
    assert _history(client, 424_242).status_code == 404


def test_an_unknown_run_is_404(client: ApiClient) -> None:
    response = client.get("/api/evals/424_242")

    assert response.status_code == 404
    assert "424242" in response.json()["detail"]


def test_an_empty_golden_set_is_422_and_persists_no_run(
    client: ApiClient, settings: Settings
) -> None:
    # Uploading seeds an empty golden file; nothing fills it in.
    document_id = _upload(client)

    response = _start(client, document_id)

    assert response.status_code == 422
    detail = response.json()["detail"].lower()
    assert "empty" in detail or "golden" in detail
    assert _history(client, document_id).json() == []


def test_an_invalid_golden_set_is_422_and_names_the_entry(
    client: ApiClient, settings: Settings
) -> None:
    document_id = _upload(client)
    path = settings.data_dir / "golden" / f"{document_id}.json"
    path.write_text(
        json.dumps([{"question": "", "expected_answer": "x", "expected_pages": [1]}]),
        encoding="utf-8",
    )

    response = _start(client, document_id)

    assert response.status_code == 422
    assert "entry 0" in response.json()["detail"]
    assert _history(client, document_id).json() == []


def test_a_missing_golden_file_is_the_domain_status(
    client: ApiClient, settings: Settings
) -> None:
    document_id = _upload(client)
    (settings.data_dir / "golden" / f"{document_id}.json").unlink()

    response = _start(client, document_id)

    assert response.status_code == 404
    assert "golden" in response.json()["detail"].lower()


def test_a_generator_failure_is_503_and_leaves_no_partial_history(
    client_for, settings: Settings
) -> None:
    failing = _FailingGenerator(fail_on=2)
    with client_for(generator=failing) as client:
        document_id = _upload(client)
        _seed_golden(settings, document_id)

        response = _start(client, document_id)
        history = _history(client, document_id)

    assert failing.calls == 2
    assert response.status_code == 503
    assert "Ollama" in response.json()["detail"]
    assert "ollama serve" in response.json()["detail"]
    assert history.status_code == 200
    assert history.json() == []


def test_an_unavailable_scorer_is_503_with_an_actionable_message(
    client_for, settings: Settings
) -> None:
    with client_for(scorer=_UnavailableScorer()) as client:
        document_id = _upload(client)
        _seed_golden(settings, document_id)

        response = _start(client, document_id)
        history = _history(client, document_id)

    assert response.status_code == 503
    detail = response.json()["detail"].lower()
    assert "scorer" in detail
    assert "unavailable" in detail
    assert history.json() == []
