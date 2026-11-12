"""Typed API models for answers and citations (T08).

These models are the REST contract shared with the frontend (SPEC "API
surface": ``POST /api/documents/{id}/ask`` returns ``{answer, citations}``).
They intentionally contain no route or service imports so both the generation
layer and the API layer can depend on them without a cycle.

The schema enforces the product promise: an answer always carries at least one
citation and every citation has a real 1-based page and a non-empty quote
(Locked intent #4, Boundaries -> Never).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


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


__all__ = ["AnswerResponse", "Citation"]
