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
from typing import Literal

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


__all__ = [
    "AnswerResponse",
    "AppConfig",
    "AskRequest",
    "Citation",
    "ConfigUpdate",
    "DeleteDocumentResponse",
    "Document",
    "DocumentDetail",
    "GeneratorChoice",
    "PageText",
]
