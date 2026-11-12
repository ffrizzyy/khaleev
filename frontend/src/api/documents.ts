/**
 * One typed function per document endpoint in SPEC's API surface.
 *
 * The paths and body shapes mirror `backend/src/khaleev/api/routes/documents.py`
 * and `routes/ask.py`; nothing here invents a field.
 */

import type {
  AnswerResponse,
  AskRequest,
  DeleteDocumentResponse,
  Document,
  DocumentDetail,
  PageText,
} from "../types";
import { apiRequest } from "./client";

/** `GET /api/documents` — every stored document, oldest first. */
export function listDocuments(): Promise<Document[]> {
  return apiRequest<Document[]>("/documents");
}

/** `GET /api/documents/{id}` — one document's metadata. */
export function getDocument(documentId: number): Promise<DocumentDetail> {
  return apiRequest<DocumentDetail>(`/documents/${documentId}`);
}

/**
 * `POST /api/documents` — multipart PDF upload.
 *
 * Returns 201 with the new document or 200 with the existing id when the same
 * bytes were already ingested; both parse the same way.
 */
export function uploadDocument(file: File): Promise<Document> {
  const formData = new FormData();
  formData.append("file", file);
  return apiRequest<Document>("/documents", { method: "POST", formData });
}

/** `GET /api/documents/{id}/pages/{n}` — one page's extracted text. */
export function getPageText(documentId: number, pageNumber: number): Promise<PageText> {
  return apiRequest<PageText>(`/documents/${documentId}/pages/${pageNumber}`);
}

/** `DELETE /api/documents/{id}` — remove the document and all of its data. */
export function deleteDocument(documentId: number): Promise<DeleteDocumentResponse> {
  return apiRequest<DeleteDocumentResponse>(`/documents/${documentId}`, { method: "DELETE" });
}

/** `POST /api/documents/{id}/ask` — a page-cited answer from that document only. */
export function askDocument(documentId: number, question: string): Promise<AnswerResponse> {
  return apiRequest<AnswerResponse>(`/documents/${documentId}/ask`, {
    method: "POST",
    json: { question } satisfies AskRequest,
  });
}
