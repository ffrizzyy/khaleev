"""The ask use case: retrieve, prompt, generate, validate citations (T09).

This module is the whole answer pipeline and nothing else: it imports the
retrieval layer, the generation layer and the document service, but **no web
framework**, so T16's eval runner (and any CLI) can reuse it unchanged. The API
route only translates what it returns and what it raises.

The product promise is enforced by ordering, not by hope:

1. the document must exist (``DocumentNotFoundError`` -> 404);
2. retrieval must return at least one page-attributed chunk, otherwise there is
   nothing to ground an answer in (``NoContextError`` -> 422) and no generator is
   even called;
3. the prompt is built from those chunks only, so a question can never be
   answered from another document (Locked intent #3);
4. ``parse_citations`` guarantees a non-empty citation list whose pages were all
   in the retrieved context (Locked intent #4, assumption A2) — an answer never
   ships without page references;
5. generator failures surface as ``GenerationError`` so the route can answer 503
   with an actionable message instead of a traceback.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from khaleev.api.schemas import AnswerResponse
from khaleev.config import Settings
from khaleev.generation import Generator, build_prompt, parse_citations
from khaleev.ingest.embedding import Embedder
from khaleev.retrieval.search import retrieve
from khaleev.services import documents


class NoContextError(Exception):
    """The document exists but has no retrievable, page-attributed text."""


def answer_question(
    session: Session,
    document_id: int,
    question: str,
    *,
    generator: Generator,
    embedder: Embedder | None = None,
    settings: Settings | None = None,
) -> AnswerResponse:
    """Answer ``question`` using only ``document_id``'s retrieved chunks.

    Raises :class:`~khaleev.services.documents.DocumentNotFoundError` for an
    unknown document, :class:`NoContextError` when retrieval finds nothing,
    ``ValueError`` for a blank question, and
    :class:`~khaleev.generation.GenerationError` when the generator cannot
    produce an answer. Every dependency is injected so tests can run the real
    pipeline with fakes and no network.
    """
    config = settings if settings is not None else Settings()
    documents.get_document(session, document_id)

    cleaned = question.strip()
    if not cleaned:
        raise ValueError("question must not be empty")

    retrieved = retrieve(
        document_id,
        cleaned,
        session=session,
        embedder=embedder,
        settings=config,
        data_dir=config.data_dir,
    )
    if not retrieved.chunks:
        raise NoContextError(
            f"document {document_id} has no indexed text to answer from; "
            "delete and re-upload the PDF so its chunks are embedded, then ask again"
        )

    prompt = build_prompt(cleaned, retrieved.chunks)
    answer = generator.generate(prompt)
    citations = parse_citations(answer, retrieved)
    return AnswerResponse(answer=answer, citations=citations)


__all__ = ["NoContextError", "answer_question"]
