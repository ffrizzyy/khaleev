/**
 * The Chat page (F3, AC2) in R1's card language (T24).
 *
 * Above the grid, a slim document context strip carries the selected
 * document's name, its page count and a route back to the Library. Below it the
 * page splits into R1's two columns: the question form, the answer and the
 * citation list are cards in the left column, and the cited page viewer is a
 * card in the right column — so at stacked widths it follows the answer.
 *
 * Behaviour is unchanged from T12: with no selection the page explains how to
 * pick a document and renders no form (so no request can be fired against
 * nothing); with a selection it names the document and scopes the panel to it
 * (Locked intent #3 — one selected document per question). The open viewer is
 * stored as the document id plus the page, and rendered only while that id is
 * still the selected document.
 */

import { useCallback, useState } from "react";
import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import { AskPanel } from "../components/AskPanel";
import { ArrowIcon } from "../components/Icons";
import { PageViewer } from "../components/PageViewer";
import { useSelectedDocument } from "../state/selectedDocument";

interface OpenPage {
  documentId: number;
  page: number;
}

export function Chat(): ReactElement {
  const selected = useSelectedDocument();
  const [openPage, setOpenPage] = useState<OpenPage | null>(null);
  const selectedId = selected?.id ?? null;

  const openCitedPage = useCallback(
    (page: number): void => {
      if (selectedId !== null) {
        setOpenPage({ documentId: selectedId, page });
      }
    },
    [selectedId],
  );

  const dismissViewer = useCallback((): void => {
    setOpenPage(null);
  }, []);

  if (selected === null) {
    return (
      <section className="page" aria-labelledby="chat-heading">
        <header className="page__header">
          <h2 className="page__title" id="chat-heading">
            Chat
          </h2>
        </header>
        <p className="page__lede">
          No document selected yet. Open the Library, pick the document you want to question, then
          come back here to ask about it.
        </p>
        <p className="page__action">
          <Link className="text-link" to="/">
            Go to the Library to pick a document
          </Link>
        </p>
      </section>
    );
  }

  const visiblePage =
    openPage !== null && openPage.documentId === selected.id ? openPage.page : null;

  return (
    <section className="page" aria-labelledby="chat-heading">
      <header className="page__header">
        <h2 className="page__title" id="chat-heading">
          Chat
        </h2>
      </header>

      <section className="context-strip" aria-label="Selected document">
        <div className="context-strip__copy">
          <h3 className="context-strip__title">Questioning {selected.title}</h3>
          <p className="context-strip__meta">
            {selected.page_count} {selected.page_count === 1 ? "page" : "pages"}
          </p>
          <p className="context-strip__lede">
            Answers cite the pages they were drawn from, and selecting a citation opens that page
            below.
          </p>
        </div>
        <p className="context-strip__action">
          <Link className="text-link" to="/">
            Back to the Library
            <ArrowIcon className="text-link__icon" />
          </Link>
        </p>
      </section>

      <div className={visiblePage === null ? "page-grid" : "page-grid page-grid--two"}>
        <div className="page-grid__main">
          <AskPanel document={selected} onOpenPage={openCitedPage} activePage={visiblePage} />
        </div>
        {visiblePage !== null ? (
          <aside className="page-grid__side" aria-label="Cited page">
            <PageViewer
              documentId={selected.id}
              pageNumber={visiblePage}
              pageCount={selected.page_count}
              onDismiss={dismissViewer}
            />
          </aside>
        ) : null}
      </div>
    </section>
  );
}
