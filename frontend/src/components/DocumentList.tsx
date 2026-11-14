/**
 * The document library list (F2): title, page count, ingest date, a select
 * control that makes one document the Q&A target, and a guarded delete.
 *
 * T23 rebuilds the list as R1's card row: one `<ul>` of `<li>` document cards
 * (list semantics unchanged, because the page tests count document rows), each
 * with a white circle icon chip, a two-line title, a meta row and its actions.
 * R1's overflow "…" control and progress track are omitted: the API exposes no
 * per-document menu and no per-document progress, so there is nothing real to
 * put in them.
 *
 * Deletion is the only destructive action in the app (it also removes chunks,
 * the vector index, the golden set and the eval history), so it is never a
 * single click: the card swaps its Delete button for an inline confirmation,
 * announced as a labelled group so screen-reader and keyboard users get the
 * same explicit choice. The row is removed by the parent after the API call
 * succeeds, so a failed delete leaves the list and the user's place intact.
 */

import { useState } from "react";
import type { ReactElement, ReactNode } from "react";

import { isApiError } from "../api/client";
import type { Document } from "../types";
import { DocumentIcon } from "./Icons";

export interface DocumentListProps {
  documents: readonly Document[];
  /** The current Q&A target, highlighted in the list. */
  selectedDocumentId: number | null;
  onSelect: (document: Document) => void;
  /** Resolves once the document is gone; rejects with the API's error. */
  onDelete: (document: Document) => Promise<void>;
  /** True when the document list has been narrowed by the search field. */
  isFiltered?: boolean;
  /**
   * Optional control for the section header, e.g. the Library's search field.
   * Rendered beside the heading — never inside the list — so the document rows
   * stay the only list items.
   */
  search?: ReactNode;
}

function pagesLabel(pageCount: number): string {
  return `${pageCount} ${pageCount === 1 ? "page" : "pages"}`;
}

/** Deterministic UTC date (the API sends ISO-8601); no locale drift in tests. */
function formatIngestDate(createdAt: string): string {
  const dateOnly = createdAt.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(dateOnly) ? dateOnly : createdAt;
}

function describeFailure(error: unknown, title: string): string {
  const reason = isApiError(error)
    ? error.detail
    : error instanceof Error
      ? error.message
      : "Unknown error";
  return `Could not delete "${title}": ${reason}`;
}

export function DocumentList({
  documents,
  selectedDocumentId,
  onSelect,
  onDelete,
  isFiltered = false,
  search,
}: DocumentListProps): ReactElement {
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<{ documentId: number; message: string } | null>(
    null,
  );

  function startConfirming(document: Document): void {
    setDeleteError(null);
    setConfirmingId(document.id);
  }

  function cancelConfirming(): void {
    setDeleteError(null);
    setConfirmingId(null);
  }

  async function confirmDelete(document: Document): Promise<void> {
    setDeleteError(null);
    setDeletingId(document.id);
    try {
      await onDelete(document);
      setConfirmingId(null);
    } catch (error) {
      setDeleteError({ documentId: document.id, message: describeFailure(error, document.title) });
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <section className="doc-section" aria-labelledby="document-list-heading">
      <div className="section-heading">
        <h3 className="section-heading__title" id="document-list-heading">
          Your documents
        </h3>
        {search}
      </div>
      {documents.length === 0 ? (
        <p className="empty-state">
          {isFiltered
            ? "No documents match your search."
            : "No documents yet. Upload a PDF to start your library."}
        </p>
      ) : (
        <ul className="doc-grid">
          {documents.map((document) => {
            const isSelected = document.id === selectedDocumentId;
            const isConfirming = document.id === confirmingId;
            const isDeleting = document.id === deletingId;
            return (
              <li
                className="doc-card"
                key={document.id}
                aria-current={isSelected ? "true" : undefined}
              >
                <span className="doc-card__chip" aria-hidden="true">
                  <DocumentIcon />
                </span>
                <div className="doc-card__body">
                  <h4 className="doc-card__title">{document.title}</h4>
                  <div className="doc-card__meta-row">
                    <p className="doc-card__meta">{pagesLabel(document.page_count)}</p>
                    <p className="doc-card__meta">
                      Ingested{" "}
                      <time dateTime={document.created_at}>
                        {formatIngestDate(document.created_at)}
                      </time>
                    </p>
                  </div>
                  {isSelected ? <p className="doc-card__badge">Selected for Q&amp;A</p> : null}
                </div>
                <div className="doc-card__actions">
                  <button
                    className="button doc-card__action"
                    type="button"
                    aria-pressed={isSelected}
                    onClick={() => onSelect(document)}
                  >
                    {isSelected ? `Selected: ${document.title}` : `Select ${document.title}`}
                  </button>
                  {isConfirming ? (
                    <div
                      className="confirm"
                      role="group"
                      aria-label={`Confirm deletion of ${document.title}`}
                    >
                      <p className="confirm__text">
                        Delete "{document.title}" and all of its eval history? This cannot be
                        undone.
                      </p>
                      <button
                        className="button button--danger"
                        type="button"
                        disabled={isDeleting}
                        onClick={() => void confirmDelete(document)}
                      >
                        Confirm delete {document.title}
                      </button>
                      <button
                        className="button"
                        type="button"
                        disabled={isDeleting}
                        onClick={cancelConfirming}
                      >
                        Cancel delete {document.title}
                      </button>
                      {isDeleting ? (
                        <p className="status" role="status">
                          Deleting "{document.title}"…
                        </p>
                      ) : null}
                    </div>
                  ) : (
                    <button
                      className="button doc-card__action"
                      type="button"
                      onClick={() => startConfirming(document)}
                    >
                      Delete {document.title}
                    </button>
                  )}
                </div>
                {deleteError?.documentId === document.id ? (
                  <p className="alert" role="alert">
                    {deleteError.message}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
