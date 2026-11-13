/**
 * The Library page (F2): upload PDFs, browse what is stored, pick the one
 * document to question, and delete a document with all of its data.
 *
 * The page owns the document list so both children stay presentational: the
 * upload control reports a document, the list reports a selection or a delete,
 * and the page decides when to refetch or update. Every API failure is caught
 * and rendered as text, so a bad response can never leave a blank screen or an
 * unhandled rejection.
 *
 * Loading is driven by a refresh token rather than an imperative function: the
 * effect owns the fetch lifecycle (and ignores a response that arrives after
 * unmount or after a newer refresh), while uploads and the retry button just
 * bump the token.
 */

import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";

import { isApiError } from "../api/client";
import { deleteDocument, listDocuments } from "../api/documents";
import { DocumentList } from "../components/DocumentList";
import { Upload } from "../components/Upload";
import {
  clearSelectedDocument,
  selectDocument,
  useSelectedDocument,
} from "../state/selectedDocument";
import type { Document } from "../types";

function describeFailure(error: unknown): string {
  if (isApiError(error)) {
    return error.detail;
  }
  return error instanceof Error ? error.message : "Unknown error";
}

export function Library(): ReactElement {
  const [documents, setDocuments] = useState<Document[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const selectedDocument = useSelectedDocument();

  const refresh = useCallback((): void => {
    setRefreshToken((token) => token + 1);
  }, []);

  useEffect(() => {
    let active = true;
    listDocuments()
      .then((next) => {
        if (!active) {
          return;
        }
        setLoadError(null);
        setDocuments(next);
      })
      .catch((error: unknown) => {
        if (active) {
          setLoadError(describeFailure(error));
        }
      });
    return () => {
      active = false;
    };
  }, [refreshToken]);

  function retryLoad(): void {
    setLoadError(null);
    refresh();
  }

  async function handleDelete(document: Document): Promise<void> {
    await deleteDocument(document.id);
    setDocuments((current) =>
      current === null ? current : current.filter((item) => item.id !== document.id),
    );
    if (selectedDocument?.id === document.id) {
      clearSelectedDocument();
    }
  }

  const loading = documents === null && loadError === null;

  return (
    <section className="page" aria-labelledby="library-heading">
      <header className="page__header">
        <h2 className="page__title" id="library-heading">
          Library
        </h2>
        <p className="page__lede">Upload a PDF, then pick the one document you want to question.</p>
      </header>

      <Upload existingDocuments={documents ?? []} onUploaded={refresh} />

      <p
        className={
          selectedDocument === null
            ? "selection-banner"
            : "selection-banner selection-banner--active"
        }
        aria-live="polite"
      >
        {selectedDocument === null
          ? "No document selected for Q&A yet."
          : `Q&A target: ${selectedDocument.title}`}
      </p>

      {loading ? (
        <p className="status" role="status">
          Loading documents…
        </p>
      ) : null}

      {loadError !== null ? (
        <div className="notice" role="alert">
          <p className="notice__text">Could not load the library: {loadError}</p>
          <button className="button" type="button" onClick={retryLoad}>
            Retry loading documents
          </button>
        </div>
      ) : null}

      {documents !== null ? (
        <DocumentList
          documents={documents}
          selectedDocumentId={selectedDocument?.id ?? null}
          onSelect={selectDocument}
          onDelete={handleDelete}
        />
      ) : null}
    </section>
  );
}
