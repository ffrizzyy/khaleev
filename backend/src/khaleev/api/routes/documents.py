"""Document library routes: upload, list, detail, page text, delete (T09).

The routes are thin on purpose. They validate transport-level concerns (a
multipart file, an integer id), delegate to ``khaleev.services.documents`` and
convert rows to the typed Pydantic models in ``khaleev.api.schemas``. Domain
errors are raised from the service and mapped to status codes by the handlers in
``khaleev.app``, so the mapping lives in exactly one place and no route leaks a
traceback.

Two status codes are contractual (SPEC "API surface", AC1): a new file is
``201``, and identical bytes are ``200`` with the existing document's id.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile, status

from khaleev.api import schemas
from khaleev.api.deps import EmbedderDep, ServicesDep, SessionDep
from khaleev.models import Document as DocumentRow
from khaleev.services import documents

router = APIRouter(prefix="/documents", tags=["documents"])

DEFAULT_FILENAME = "document.pdf"


def _as_document(document: DocumentRow) -> schemas.Document:
    """The list/detail view of a row."""
    return schemas.Document(
        id=document.id,
        title=document.title,
        page_count=document.page_count,
        created_at=document.created_at,
    )


def _as_detail(document: DocumentRow) -> schemas.DocumentDetail:
    """The single-document view, which also carries the dedupe key."""
    return schemas.DocumentDetail(
        id=document.id,
        title=document.title,
        page_count=document.page_count,
        created_at=document.created_at,
        content_hash=document.content_hash,
    )


@router.post(
    "",
    response_model=schemas.Document,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {
            "model": schemas.Document,
            "description": "Identical bytes were already ingested; returns the existing document",
        }
    },
)
def upload_document(
    response: Response,
    file: Annotated[UploadFile, File(description="The PDF to ingest")],
    session: SessionDep,
    services: ServicesDep,
    embedder: EmbedderDep,
) -> schemas.Document:
    """Ingest an uploaded PDF, embedding its chunks so retrieval can find them.

    Raises the ingest domain errors (``NotAPdfError`` -> 400,
    ``CorruptPdfError`` -> 422) instead of returning a broken document.
    """
    payload = file.file.read()
    result = documents.upload_document(
        session,
        pdf_bytes=payload,
        filename=file.filename or DEFAULT_FILENAME,
        settings=services.settings,
        embedder=embedder,
    )
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return _as_document(result.document)


@router.get("", response_model=list[schemas.Document])
def list_documents(session: SessionDep) -> list[schemas.Document]:
    """Every stored document, oldest first."""
    return [_as_document(document) for document in documents.list_documents(session)]


@router.get("/{document_id}", response_model=schemas.DocumentDetail)
def get_document(document_id: int, session: SessionDep) -> schemas.DocumentDetail:
    """One document's metadata; 404 when the id is unknown."""
    return _as_detail(documents.get_document(session, document_id))


@router.get("/{document_id}/pages/{page_number}", response_model=schemas.PageText)
def get_page_text(
    document_id: int,
    page_number: int,
    session: SessionDep,
    services: ServicesDep,
) -> schemas.PageText:
    """One page's extracted text, rebuilt from that page's stored chunks."""
    text = documents.page_text(session, document_id, page_number, services.settings)
    return schemas.PageText(document_id=document_id, page_number=page_number, text=text)


@router.delete("/{document_id}", response_model=schemas.DeleteDocumentResponse)
def delete_document(
    document_id: int, session: SessionDep, services: ServicesDep
) -> schemas.DeleteDocumentResponse:
    """Delete a document, its eval history, its vectors, its PDF and its golden file."""
    documents.delete_document(session, document_id, settings=services.settings)
    return schemas.DeleteDocumentResponse(id=document_id, deleted=True)
