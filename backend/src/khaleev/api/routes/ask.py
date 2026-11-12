"""The ask route: one question, one document, a page-cited answer (T09, AC2).

Everything that matters happens in ``khaleev.services.qa`` — this route only
validates the body, passes the injected generator and embedder, and returns the
typed ``AnswerResponse``. An unknown document is a 404, a document without
indexed text is a 422 and an unreachable generator is a 503, all mapped centrally
in ``khaleev.app``.
"""

from __future__ import annotations

from fastapi import APIRouter

from khaleev.api import schemas
from khaleev.api.deps import EmbedderDep, GeneratorDep, ServicesDep, SessionDep
from khaleev.services.qa import answer_question

router = APIRouter(prefix="/documents", tags=["ask"])


@router.post("/{document_id}/ask", response_model=schemas.AnswerResponse)
def ask(
    document_id: int,
    request: schemas.AskRequest,
    session: SessionDep,
    services: ServicesDep,
    embedder: EmbedderDep,
    generator: GeneratorDep,
) -> schemas.AnswerResponse:
    """Answer ``request.question`` from ``document_id``'s retrieved chunks only."""
    return answer_question(
        session,
        document_id,
        request.question,
        generator=generator,
        embedder=embedder,
        settings=services.settings,
    )
