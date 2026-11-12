"""Typed API models: the REST contract shared with the frontend.

These models are the contract of SPEC's "API surface". They intentionally
contain no route or service imports so the generation layer, the services and the
API layer can all depend on them without a cycle.

Two guarantees live in the schema itself, so no route can forget them:

* an answer always carries at least one citation, and every citation has a real
  1-based page and a non-empty quote (Locked intent #4, Boundaries -> Never);
* every request body is validated (``k >= 1``, a non-blank question, a known
  generator choice) and every response is a typed model, never a bare dict.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

GeneratorChoice = Literal["ollama", "cloud"]


class Citation(BaseModel):
    """One source reference: the 1-based page and a supporting quote."""

    page: int = Field(ge=1, description="1-based source page number")
    quote: str = Field(min_length=1, description="Verbatim or excerpted source text")

    @field_validator("quote")
    @classmethod
    def _quote_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("citation quote must not be blank")
        return value


class AnswerResponse(BaseModel):
    """A grounded answer: prose plus at least one page citation."""

    answer: str = Field(min_length=1)
    citations: list[Citation] = Field(min_length=1)

    @field_validator("answer")
    @classmethod
    def _answer_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("answer must not be blank")
        return value


class AskRequest(BaseModel):
    """A natural-language question about one selected document."""

    question: str = Field(min_length=1, description="The question to answer")

    @field_validator("question")
    @classmethod
    def _question_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value


class Document(BaseModel):
    """A library row: what ``GET /api/documents`` lists."""

    id: int
    title: str
    page_count: int = Field(ge=1)
    created_at: datetime


class DocumentDetail(Document):
    """A single document plus the dedupe key the list does not need."""

    content_hash: str


class PageText(BaseModel):
    """One page's extracted text, rebuilt from that page's stored chunks."""

    document_id: int
    page_number: int = Field(ge=1)
    text: str


class DeleteDocumentResponse(BaseModel):
    """The outcome of a delete; the row and its files are gone when ``deleted``."""

    id: int
    deleted: bool


class GoldenEntry(BaseModel):
    """One curated question, its expected answer and its 1-based source pages."""

    question: str = Field(min_length=1)
    expected_answer: str = Field(min_length=1)
    expected_pages: list[int] = Field(min_length=1, description="1-based page numbers")

    @field_validator("question", "expected_answer")
    @classmethod
    def _text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("golden entry text must not be blank")
        return value


class GoldenSet(BaseModel):
    """A document's golden set as the UI reads it (F4, AC4)."""

    document_id: int
    revision: str = Field(
        min_length=1, description="Content hash of the golden-set file, used for comparability"
    )
    entries: list[GoldenEntry] = Field(min_length=1)


class AppConfig(BaseModel):
    """The settings the UI may read: retrieval size and model choices."""

    k: int = Field(ge=1, description="Top-k retrieved chunks per question")
    embedder: str = Field(min_length=1, description="Embedding model id")
    generator: GeneratorChoice
    ollama_base_url: str
    ollama_model: str


class ConfigUpdate(BaseModel):
    """A partial config update; omitted fields keep their current value."""

    k: int | None = Field(default=None, ge=1)
    embedder: str | None = Field(default=None, min_length=1)
    generator: GeneratorChoice | None = None


class StartEvalRequest(BaseModel):
    """The optional body of ``POST /api/documents/{id}/evals``.

    ``k`` omitted means "use the server's configured retrieval size" — the
    default 5 — and the run records whichever ``k`` it actually used, so
    hit-rate@k stays comparable across runs (Metric definitions, AC10).
    """

    k: int | None = Field(default=None, ge=1, description="Top-k for this run")


class EvalRunEntry(BaseModel):
    """One golden entry's persisted result inside an eval run (AC5)."""

    golden_index: int = Field(ge=0)
    hit: bool
    answer: str
    claims: int = Field(ge=0)
    supported_claims: int = Field(ge=0)
    faithfulness: float = Field(ge=0.0, le=1.0)


class EvalRun(BaseModel):
    """A persisted eval run with its aggregate metrics and recorded config (F5)."""

    id: int
    document_id: int
    created_at: datetime
    k: int = Field(ge=1, description="Top-k used by the run")
    embedder_id: str = Field(min_length=1)
    scorer_id: str = Field(min_length=1)
    hit_rate: float = Field(ge=0.0, le=1.0)
    faithfulness: float = Field(ge=0.0, le=1.0)
    config: dict[str, Any] = Field(
        description="Persisted run configuration, including the golden-set revision"
    )


class EvalRunDetail(EvalRun):
    """A single run read back with one row per golden entry (AC5)."""

    entries: list[EvalRunEntry]


class EvalRunSummary(EvalRun):
    """A history row: the run plus its comparability flag (AC6, AC10).

    ``flagged`` is computed by the backend from the persisted config only;
    ``comparable`` is its inverse, both exposed so the dashboard never has to
    re-derive the rule.
    """

    comparable: bool
    flagged: bool


__all__ = [
    "AnswerResponse",
    "AppConfig",
    "AskRequest",
    "Citation",
    "ConfigUpdate",
    "DeleteDocumentResponse",
    "Document",
    "DocumentDetail",
    "EvalRun",
    "EvalRunDetail",
    "EvalRunEntry",
    "EvalRunSummary",
    "GeneratorChoice",
    "GoldenEntry",
    "GoldenSet",
    "PageText",
    "StartEvalRequest",
]
