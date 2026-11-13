"""One walk through the whole user journey, offline (AC9, AC10).

This is the loop-closing test: upload a real PDF, ask a question and get an answer
with page citations, run an eval against a curated golden set, read back both
persisted metrics, then run a second eval with a different ``k`` and see the two
runs in the history — the newer one comparable, the older one flagged because the
persisted configs disagree.

Everything model-backed is a fake (``FakeEmbedder``, ``FakeGenerator``,
``FakeEntailmentScorer``) and the app is built with ``create_app``, so the journey
is the real request → service → database path with no model and no socket (SPEC
AC8, Locked intent #12). The numbers are deterministic: the third golden entry
expects page 99, which no retrieved chunk can carry, so hit rate is 2/3; the
repeating answer is one supported claim, so faithfulness is 1.0.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fixtures.api_client import ApiClient
from fixtures.pdf_factory import build_pdf
from sqlalchemy.engine import Engine

from khaleev.app import create_app
from khaleev.config import Settings
from khaleev.evals.golden import write_golden_file
from khaleev.evals.scorer import FakeEntailmentScorer
from khaleev.generation import FakeGenerator
from khaleev.ingest.embedding import FakeEmbedder

QUESTION = "What penalty applies to late filings?"
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
#: Repeats for the ask and every eval entry; the page tag is a retrieved page.
ANSWER = "Late filings incur a 200 credit penalty. [page 1]"

HIT_RATE_WITH_ONE_MISS = 0.6667
FAITHFULNESS_WITH_ONE_SUPPORTED_CLAIM = 1.0


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)


@pytest.fixture
def app(settings: Settings, migrated_engine: Engine) -> FastAPI:
    return create_app(
        settings=settings,
        embedder=FakeEmbedder(),
        generator=FakeGenerator(ANSWER),
        scorer=FakeEntailmentScorer(default=True),
    )


@pytest.fixture
def client(app: FastAPI) -> Iterator[ApiClient]:
    with ApiClient(app) as client:
        yield client


def test_upload_ask_eval_and_flagged_history(client: ApiClient, settings: Settings) -> None:
    # 1. Upload a real multi-page PDF through the API.
    upload = client.post(
        "/api/documents",
        files={"file": ("tax-guide.pdf", build_pdf(PAGES), "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    document_id = int(upload.json()["id"])
    assert upload.json()["page_count"] == len(PAGES)
    assert [document["id"] for document in client.get("/api/documents").json()] == [document_id]

    # 2. Ask a question and receive a page-cited answer.
    asked = client.post(f"/api/documents/{document_id}/ask", json={"question": QUESTION})
    assert asked.status_code == 200, asked.text
    answer = asked.json()
    assert answer["answer"].strip()
    assert answer["citations"], "an answer without page citations is a defect"
    for citation in answer["citations"]:
        assert 1 <= citation["page"] <= len(PAGES)
        assert citation["quote"].strip()

    # 3. The user curates the golden set on disk, then runs an eval.
    write_golden_file(settings.data_dir, document_id, GOLDEN_ENTRIES)
    first = client.post(f"/api/documents/{document_id}/evals", json={"k": 5})
    assert first.status_code == 200, first.text
    first_run = first.json()
    assert first_run["document_id"] == document_id
    assert first_run["k"] == 5
    assert first_run["hit_rate"] == HIT_RATE_WITH_ONE_MISS
    assert first_run["faithfulness"] == FAITHFULNESS_WITH_ONE_SUPPORTED_CLAIM
    for metric in ("hit_rate", "faithfulness"):
        assert 0.0 <= first_run[metric] <= 1.0

    # 4. Both metrics and every per-entry result are persisted and readable back.
    detail = client.get(f"/api/evals/{first_run['id']}")
    assert detail.status_code == 200, detail.text
    detail_body = detail.json()
    assert detail_body["hit_rate"] == first_run["hit_rate"]
    assert detail_body["faithfulness"] == first_run["faithfulness"]
    assert [entry["golden_index"] for entry in detail_body["entries"]] == [0, 1, 2]
    assert [entry["hit"] for entry in detail_body["entries"]] == [True, True, False]

    # 5. A second run with a different k: the same document, a changed config.
    second = client.post(f"/api/documents/{document_id}/evals", json={"k": 10})
    assert second.status_code == 200, second.text
    second_run = second.json()
    assert second_run["id"] != first_run["id"]
    assert second_run["hit_rate"] == HIT_RATE_WITH_ONE_MISS
    assert second_run["faithfulness"] == FAITHFULNESS_WITH_ONE_SUPPORTED_CLAIM

    # 6. The dashboard history carries both runs, newest first, and flags the
    #    one whose persisted k differs instead of silently comparing them (AC10).
    history = client.get(f"/api/documents/{document_id}/evals")
    assert history.status_code == 200, history.text
    rows = history.json()

    assert [row["id"] for row in rows] == [second_run["id"], first_run["id"]]
    assert [row["k"] for row in rows] == [10, 5]
    assert [row["flagged"] for row in rows] == [False, True]
    assert [row["comparable"] for row in rows] == [True, False]
    for row in rows:
        assert row["created_at"]
        assert row["hit_rate"] == HIT_RATE_WITH_ONE_MISS
        assert row["faithfulness"] == FAITHFULNESS_WITH_ONE_SUPPORTED_CLAIM
