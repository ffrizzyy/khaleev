"""Integration tests for the ask endpoint (T09, AC2).

The whole path is exercised end to end: a document is uploaded through the API
(so the upload route's embedder actually runs), then a question is asked and the
answer's citations are checked against the retrieval context. That pairing is
deliberate: T06 left a gap where an upload without an embedder stores unembedded
chunks and retrieval silently returns nothing, and only upload -> ask catches it.

Both model-backed dependencies are fakes (``FakeEmbedder``, ``FakeGenerator``) and
the app is built with ``create_app``, so no model is loaded and the socket guard
never sees a connection (SPEC AC8, Locked intent #12).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Protocol

import pytest
from fastapi import FastAPI
from fixtures.api_client import ApiClient
from fixtures.pdf_factory import build_pdf
from sqlalchemy.engine import Engine

from khaleev.app import create_app
from khaleev.config import Settings
from khaleev.db import create_session_factory
from khaleev.generation import FakeGenerator, GenerationError
from khaleev.ingest.embedding import FakeEmbedder
from khaleev.models import Document
from khaleev.retrieval.search import retrieve

QUESTION = "What penalty applies to late filings?"
PAGE_TEXTS = [
    "Late filings incur a 200 credit penalty per return.",
    "Refunds are processed within ten business days.",
    "Appeals must be filed within thirty days of the notice.",
]


class _Generator(Protocol):
    def generate(self, prompt: str) -> str: ...


class _UnreachableGenerator:
    """A generator whose backend is down, for the 503 mapping."""

    def generate(self, prompt: str) -> str:
        raise GenerationError(
            "could not reach Ollama at http://localhost:11434/api/generate: "
            "connection refused. Is Ollama running? Start it with `ollama serve` and retry."
        )


def _upload(client: ApiClient, pages: list[str], name: str = "tax-guide.pdf") -> int:
    response = client.post(
        "/api/documents",
        files={"file": (name, build_pdf(pages), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _ask(client: ApiClient, document_id: int, question: str = QUESTION):
    return client.post(f"/api/documents/{document_id}/ask", json={"question": question})


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def generator() -> FakeGenerator:
    return FakeGenerator()


@pytest.fixture
def app(
    migrated_engine: Engine,
    settings: Settings,
    embedder: FakeEmbedder,
    generator: FakeGenerator,
) -> FastAPI:
    """The real app with both model-backed dependencies faked."""
    return create_app(settings=settings, embedder=embedder, generator=generator)


@pytest.fixture
def client(app: FastAPI) -> Iterator[ApiClient]:
    with ApiClient(app) as client:
        yield client


@pytest.fixture
def client_for(
    migrated_engine: Engine, settings: Settings, embedder: FakeEmbedder
) -> Callable[[_Generator], ApiClient]:
    """Build extra app clients with a different scripted generator."""

    def build(active_generator: _Generator) -> ApiClient:
        return ApiClient(
            create_app(settings=settings, embedder=embedder, generator=active_generator)
        )

    return build


def _retrieved_pages(
    migrated_engine: Engine, settings: Settings, embedder: FakeEmbedder, document_id: int
) -> set[int]:
    """The pages of the exact retrieval context the ask path must have used."""
    with create_session_factory(migrated_engine)() as session:
        result = retrieve(
            document_id,
            QUESTION,
            session=session,
            embedder=embedder,
            settings=settings,
            data_dir=settings.data_dir,
        )
    return {chunk.page_number for chunk in result.chunks}


# --- happy path -----------------------------------------------------------


def test_upload_then_ask_returns_an_answer_with_page_citations(client: ApiClient) -> None:
    document_id = _upload(client, PAGE_TEXTS)

    response = _ask(client, document_id)

    assert response.status_code == 200
    body = response.json()
    assert body["answer"].strip()
    assert body["citations"]
    for citation in body["citations"]:
        assert 1 <= citation["page"] <= len(PAGE_TEXTS)
        assert citation["quote"].strip()
    assert client.get("/api/documents").json() != []


def test_every_cited_page_comes_from_the_retrieved_context(
    client: ApiClient,
    migrated_engine: Engine,
    settings: Settings,
    embedder: FakeEmbedder,
) -> None:
    document_id = _upload(client, PAGE_TEXTS)
    retrieved_pages = _retrieved_pages(migrated_engine, settings, embedder, document_id)

    response = _ask(client, document_id)

    assert {citation["page"] for citation in response.json()["citations"]} <= retrieved_pages


def test_the_prompt_receives_the_retrieved_excerpts_with_their_pages(
    client: ApiClient, generator: FakeGenerator
) -> None:
    document_id = _upload(client, PAGE_TEXTS)

    _ask(client, document_id)

    assert len(generator.prompts) == 1
    prompt = generator.prompts[0]
    assert QUESTION in prompt
    assert "[excerpt 1" in prompt
    assert "page " in prompt


def test_only_the_selected_documents_text_reaches_the_generator(
    client: ApiClient, generator: FakeGenerator
) -> None:
    first = _upload(client, ["ALPHAMARK late filings incur a penalty."], name="alpha.pdf")
    _upload(client, ["BETAMARK refunds are processed in ten days."], name="beta.pdf")

    _ask(client, first)

    assert generator.prompts
    assert "ALPHAMARK" in generator.prompts[0]
    assert "BETAMARK" not in generator.prompts[0]


def test_a_config_update_changes_the_retrieval_size(
    client: ApiClient,
    migrated_engine: Engine,
    settings: Settings,
    embedder: FakeEmbedder,
) -> None:
    document_id = _upload(client, PAGE_TEXTS)
    assert client.put("/api/config", json={"k": 1}).status_code == 200

    response = _ask(client, document_id)

    assert response.status_code == 200
    with create_session_factory(migrated_engine)() as session:
        retrieved = retrieve(
            document_id,
            QUESTION,
            session=session,
            embedder=embedder,
            settings=settings,
            data_dir=settings.data_dir,
        )
    assert retrieved.k == 1
    assert {citation["page"] for citation in response.json()["citations"]} == {
        retrieved.chunks[0].page_number
    }


# --- citation repair ------------------------------------------------------


def test_a_hallucinated_page_is_never_returned_as_a_citation(
    client_for, migrated_engine: Engine, settings: Settings, embedder: FakeEmbedder
) -> None:
    scripted = FakeGenerator("Late filings incur a penalty. [page 99]")
    with client_for(scripted) as client:
        document_id = _upload(client, PAGE_TEXTS)
        retrieved_pages = _retrieved_pages(migrated_engine, settings, embedder, document_id)

        response = _ask(client, document_id)

    assert response.status_code == 200
    citations = response.json()["citations"]
    assert citations
    assert {citation["page"] for citation in citations} <= retrieved_pages
    assert all(citation["page"] != 99 for citation in citations)


# --- domain errors --------------------------------------------------------


def test_ask_on_an_unknown_document_is_404(client: ApiClient) -> None:
    response = _ask(client, 424_242)

    assert response.status_code == 404


def test_ask_on_a_document_without_indexed_text_is_422(
    client: ApiClient,
    migrated_engine: Engine,
    generator: FakeGenerator,
) -> None:
    with create_session_factory(migrated_engine)() as session:
        document = Document(content_hash="no-chunks-hash", title="empty.pdf", page_count=1)
        session.add(document)
        session.commit()
        document_id = document.id

    response = _ask(client, document_id)

    assert response.status_code == 422
    assert "text" in response.json()["detail"]
    assert generator.prompts == []  # no answer is invented from an empty context


def test_an_unreachable_generator_is_503_with_an_actionable_message(
    client_for, migrated_engine: Engine
) -> None:
    with client_for(_UnreachableGenerator()) as client:
        document_id = _upload(client, PAGE_TEXTS)

        response = _ask(client, document_id)

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "Ollama" in detail
    assert "ollama serve" in detail


@pytest.mark.parametrize("payload", [{}, {"question": ""}, {"question": "   "}])
def test_a_blank_question_is_422(client: ApiClient, payload: dict[str, str]) -> None:
    document_id = _upload(client, PAGE_TEXTS)

    response = client.post(f"/api/documents/{document_id}/ask", json=payload)

    assert response.status_code == 422


def test_selecting_cloud_without_a_key_is_503_not_a_crash(migrated_engine: Engine) -> None:
    """A missing key must be an actionable 503, never a 500 traceback (AC3)."""
    settings = Settings(_env_file=None, generator="cloud")
    with ApiClient(create_app(settings=settings, embedder=FakeEmbedder())) as client:
        document_id = _upload(client, PAGE_TEXTS)
        # No API key anywhere, and the upload already worked: the app stays usable.
        assert client.get("/api/config").status_code == 200

        response = _ask(client, document_id)

    assert response.status_code == 503
    assert "KHALEEV_CLOUD_API_KEY" in response.json()["detail"]
