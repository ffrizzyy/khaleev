/**
 * The Library page (F2) — the minimal landing of locked intent 17.
 *
 * The page is upload + documents, nothing else: a simplified hero (the product
 * promise, one supporting line and the `Upload PDF` control), the selection
 * banner that names the Q&A target, and the "Your documents" list. The
 * two-across "Selected document" row and the "Latest eval run" card are gone
 * with the redesign, so the page reads exactly one endpoint — `GET
 * /api/documents` — and its column is the full width of the page shell.
 *
 * The search field lives in the "Your documents" section header and is rendered
 * only when the library holds at least one document. The count is taken before
 * filtering, so narrowing the list to zero results keeps the field usable. It
 * only filters the already-loaded list client-side — SPEC has no search
 * endpoint, and typing issues no request.
 *
 * Two elements survive deliberately: the selection banner (it is the only place
 * the user sees which document is the Q&A target, and `Library.test.tsx` — a
 * pre-existing file this task may not edit — asserts both of its strings; it is
 * rendered only when at least one document exists, because an empty library has
 * nothing to select) and the "Library" kicker (`App.test.tsx` needs exactly one
 * heading with that name). Loading states use `aria-busy` plus plain text, never
 * a new live region, because that same test asserts no `role="status"` once the
 * list has loaded.
 *
 * The loaded list is authoritative for the Q&A target: `rememberDocuments` runs
 * on every successful list (and after a delete), so a persisted id whose
 * document is gone is discarded silently before the list renders. A deleted
 * document is not an error, so nothing on this page says "does not exist"; a
 * genuine failure to load the list still does.
 */

import { useCallback, useEffect, useId, useState } from "react";
import type { ChangeEvent, ReactElement } from "react";

import { isApiError } from "../api/client";
import { deleteDocument, listDocuments } from "../api/documents";
import { DocumentList } from "../components/DocumentList";
import { SearchIcon } from "../components/Icons";
import { Upload } from "../components/Upload";
import { setSearchQuery, useSearchQuery } from "../state/searchQuery";
import { rememberDocuments, selectDocument, useSelectedDocument } from "../state/selectedDocument";
import type { Document } from "../types";

function describeFailure(error: unknown): string {
  if (isApiError(error)) {
    return error.detail;
  }
  return error instanceof Error ? error.message : "Unknown error";
}

function filterDocuments(documents: readonly Document[], query: string): Document[] {
  const needle = query.trim().toLocaleLowerCase();
  if (needle === "") {
    return [...documents];
  }
  return documents.filter((document) => document.title.toLocaleLowerCase().includes(needle));
}

/**
 * The Library's search field, mounted in the "Your documents" section header.
 *
 * It is a real labelled `<input type="search">` with the accessible name
 * "Search documents"; its value is the shared query store, so the filter
 * survives a remount. The pill carries the visible focus ring (`:focus-within`),
 * and at 360 it takes its own full-width row instead of clipping the value.
 */
function SearchDocuments(): ReactElement {
  const inputId = useId();
  const query = useSearchQuery();

  function handleChange(event: ChangeEvent<HTMLInputElement>): void {
    setSearchQuery(event.currentTarget.value);
  }

  return (
    <div className="search">
      <SearchIcon className="search__icon" />
      <label className="visually-hidden" htmlFor={inputId}>
        Search documents
      </label>
      <input
        className="search__input"
        id={inputId}
        type="search"
        placeholder="Search documents"
        autoComplete="off"
        value={query}
        onChange={handleChange}
      />
    </div>
  );
}

export function Library(): ReactElement {
  const [documents, setDocuments] = useState<Document[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const selectedDocument = useSelectedDocument();
  const searchQuery = useSearchQuery();

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
        // The fetched list is authoritative: a persisted Q&A target that is no
        // longer in it is discarded before the list is rendered, so no stale
        // title and no "document … does not exist" text can reach the page.
        rememberDocuments(next);
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
    const remaining =
      documents === null ? null : documents.filter((item) => item.id !== document.id);
    // The list stays authoritative: if the deleted document was the Q&A target,
    // recording the remaining documents clears it silently.
    if (remaining !== null) {
      rememberDocuments(remaining);
    }
    setDocuments(remaining);
  }

  const loading = documents === null && loadError === null;
  const visibleDocuments = documents === null ? [] : filterDocuments(documents, searchQuery);
  // Counted before filtering: the field stays while a filter matches nothing.
  const hasDocuments = documents !== null && documents.length > 0;

  return (
    <section className="page" aria-labelledby="library-heading">
      <section className="hero">
        <div className="hero__copy">
          <h2 className="hero__kicker" id="library-heading">
            Library
          </h2>
          <p className="hero__headline">Local-first document Q&amp;A with page-cited answers.</p>
          <p className="hero__lede">
            Upload a PDF, then pick the one document you want to question.
          </p>
          <Upload existingDocuments={documents ?? []} onUploaded={refresh} />
        </div>
      </section>

      {hasDocuments ? (
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
      ) : null}

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
          documents={visibleDocuments}
          isFiltered={searchQuery.trim() !== ""}
          selectedDocumentId={selectedDocument?.id ?? null}
          onSelect={selectDocument}
          onDelete={handleDelete}
          search={hasDocuments ? <SearchDocuments /> : undefined}
        />
      ) : null}
    </section>
  );
}
