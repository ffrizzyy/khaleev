/**
 * The page viewer (F3, AC2): reads one cited page's extracted text.
 *
 * Two safety rules are structural rather than cosmetic, because the product
 * promise is "the page you clicked is the page you see":
 *
 * 1. a page outside `1…pageCount` is refused before any request is sent, and
 * 2. loaded text is stored under the exact `documentId:pageNumber` request key
 *    and rendered only while that key is still the one on screen. A slow
 *    response for a page the user already navigated away from can therefore
 *    never replace the current page's text, and a payload whose own
 *    `page_number` disagrees with the request is rejected instead of shown.
 *
 * The viewer is a non-modal `dialog` region, so it does not trap the user: it
 * takes focus on open, closes with Escape or its button, and leaves the rest of
 * the chat usable behind it.
 */

import { useEffect, useId, useRef, useState } from "react";
import type { ReactElement } from "react";

import { isApiError } from "../api/client";
import { getPageText } from "../api/documents";
import type { PageText } from "../types";

export interface PageViewerProps {
  documentId: number;
  /** The 1-based page the user cited and asked to read. */
  pageNumber: number;
  /** The document's page count; a page outside 1…pageCount is refused. */
  pageCount: number;
  onDismiss: () => void;
}

type LoadedPage = { key: string; page: PageText };
type LoadFailure = { key: string; message: string };

function isValidPage(pageNumber: number, pageCount: number): boolean {
  return Number.isInteger(pageNumber) && pageNumber >= 1 && pageNumber <= pageCount;
}

function describeFailure(error: unknown): string {
  if (isApiError(error)) {
    return error.detail;
  }
  return error instanceof Error ? error.message : "Unknown error";
}

export function PageViewer({
  documentId,
  pageNumber,
  pageCount,
  onDismiss,
}: PageViewerProps): ReactElement {
  const headingId = useId();
  const dialogRef = useRef<HTMLElement | null>(null);
  const [loaded, setLoaded] = useState<LoadedPage | null>(null);
  const [failure, setFailure] = useState<LoadFailure | null>(null);

  const requestKey = `${documentId}:${pageNumber}`;
  const valid = isValidPage(pageNumber, pageCount);

  // Move focus into the viewer as soon as it opens (and when the cited page
  // changes) so keyboard users land where the new content is.
  useEffect(() => {
    dialogRef.current?.focus();
  }, [documentId, pageNumber]);

  // Escape closes the viewer from anywhere inside it, including the text area.
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        event.preventDefault();
        onDismiss();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onDismiss]);

  useEffect(() => {
    if (!valid) {
      return undefined;
    }
    let active = true;
    getPageText(documentId, pageNumber)
      .then((page) => {
        if (!active) {
          return;
        }
        if (page.document_id === documentId && page.page_number === pageNumber) {
          setLoaded({ key: requestKey, page });
        } else {
          setFailure({
            key: requestKey,
            message:
              `The server sent text for a different page (${page.page_number}) than the one cited ` +
              `(${pageNumber}); refusing to show it.`,
          });
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setFailure({ key: requestKey, message: describeFailure(error) });
        }
      });
    return () => {
      active = false;
    };
  }, [documentId, pageNumber, requestKey, valid]);

  const shownPage = loaded !== null && loaded.key === requestKey ? loaded.page : null;
  const shownFailure = failure !== null && failure.key === requestKey ? failure.message : null;

  let body: ReactElement;
  if (!valid) {
    body = (
      <p className="alert" role="alert">
        Page {pageNumber} is outside this document&apos;s 1–{pageCount} page range, so it cannot be
        shown. Pick one of the cited pages instead.
      </p>
    );
  } else if (shownFailure !== null) {
    body = (
      <p className="alert" role="alert">
        Could not load page {pageNumber}: {shownFailure}
      </p>
    );
  } else if (shownPage !== null) {
    body = (
      <div className="page-viewer__body">
        <p className="page-viewer__label">Extracted text for page {pageNumber}:</p>
        <p className="page-viewer__text">{shownPage.text}</p>
      </div>
    );
  } else {
    body = (
      <p className="status" role="status">
        Loading page {pageNumber}…
      </p>
    );
  }

  return (
    <section
      ref={dialogRef}
      className="page-viewer"
      role="dialog"
      aria-labelledby={headingId}
      tabIndex={-1}
    >
      <h3 className="page-viewer__title" id={headingId}>
        Page {pageNumber}
      </h3>
      {body}
      <button className="button" type="button" onClick={onDismiss}>
        Close page viewer
      </button>
    </section>
  );
}
