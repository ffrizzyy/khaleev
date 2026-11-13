/**
 * The Chat page (F3, AC2): the selected document's header, the ask panel, and
 * the cited page viewer.
 *
 * Two states, both explicit: with no selection the page explains how to pick a
 * document and renders no form (so no request can be fired against nothing);
 * with a selection it names the document and scopes the panel to it (Locked
 * intent #3 — one selected document per question).
 *
 * The open viewer is stored as the document id plus the page, and rendered only
 * while that id is still the selected document, so switching documents can never
 * leave a viewer showing another document's page.
 */

import { useCallback, useState } from "react";
import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import { AskPanel } from "../components/AskPanel";
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
      <header className="chat-context">
        <h3 className="chat-context__title">Questioning {selected.title}</h3>
        <p className="chat-context__meta">
          {selected.page_count} {selected.page_count === 1 ? "page" : "pages"}
        </p>
        <p className="chat-context__lede">
          Answers cite the pages they were drawn from, and selecting a citation opens that page
          below.
        </p>
      </header>
      <AskPanel document={selected} onOpenPage={openCitedPage} activePage={visiblePage} />
      {visiblePage !== null ? (
        <PageViewer
          documentId={selected.id}
          pageNumber={visiblePage}
          pageCount={selected.page_count}
          onDismiss={dismissViewer}
        />
      ) : null}
    </section>
  );
}
