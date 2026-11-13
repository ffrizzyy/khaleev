/**
 * The structured citation list (F3, AC2): one discrete, keyboard-reachable
 * reference per source page instead of page numbers buried in prose.
 *
 * Every citation is a real `<button>`, not a styled span, so it is focusable,
 * announced as a button, and activates with Enter or Space. The visible label is
 * the page number itself, so the accessible name always contains the number the
 * user sees (WCAG 2.5.3). The quote is shown next to its page so the user can
 * judge the evidence before opening the page, and `aria-pressed` tells a screen
 * reader which citation's page is currently open in the viewer.
 */

import { useId } from "react";
import type { ReactElement } from "react";

import type { Citation } from "../types";

export interface CitationListProps {
  citations: readonly Citation[];
  /** Called with the 1-based page number of the activated citation. */
  onOpenPage: (pageNumber: number) => void;
  /** The page currently shown in the viewer, if any, highlighted as pressed. */
  activePage?: number | null;
}

export function CitationList({
  citations,
  onOpenPage,
  activePage = null,
}: CitationListProps): ReactElement | null {
  const headingId = useId();

  if (citations.length === 0) {
    // An uncited answer is a defect the parent renders explicitly; an empty
    // list here would be a meaningless blank block.
    return null;
  }

  return (
    <section className="citations" aria-labelledby={headingId}>
      <h4 className="citations__heading" id={headingId}>
        Citations
      </h4>
      <p className="citations__hint">
        Each page below was in the retrieved context. Select one to read that page.
      </p>
      <ul className="citations__list">
        {citations.map((citation, index) => (
          <li className="citation" key={`${citation.page}-${index}`}>
            <button
              className="citation__chip"
              type="button"
              aria-pressed={citation.page === activePage}
              onClick={() => onOpenPage(citation.page)}
            >
              Page {citation.page}
            </button>
            {citation.quote.trim().length > 0 ? (
              <blockquote className="citation__quote">
                <p>{citation.quote}</p>
              </blockquote>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
