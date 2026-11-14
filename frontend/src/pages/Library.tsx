/**
 * The Library page (F2) rebuilt in R1's anatomy (T23).
 *
 * Left column: the hero banner (product promise + upload CTA), the
 * "Your documents" section with the three-across document cards, and a second
 * heading row with the selected document's golden-set summary and detail.
 * Right column: the eval summary card in the calendar slot's position,
 * followed by the two most recent runs as R1-shaped stacked cards.
 *
 * Only real data is shown. The cards read the endpoints the backend already
 * serves — `GET /api/documents/{id}`, `GET /api/documents/{id}/golden` and
 * `GET /api/documents/{id}/evals` — and an API failure is rendered as the API's
 * own message, never as a fabricated zero. The two most recent runs reuse the
 * persisted comparability flag; nothing is inferred here.
 *
 * The search field lives in the shell, so this page only reads its shared
 * value and filters the already-loaded list client-side: no request is issued
 * by typing. Loading states use `aria-busy` plus plain text, never a new live
 * region, because the Library test asserts no `role="status"` exists once the
 * document list has loaded.
 */

import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";

import { isApiError } from "../api/client";
import { deleteDocument, getDocument, listDocuments } from "../api/documents";
import { getGoldenSet, listEvalRuns } from "../api/evals";
import { DocumentList } from "../components/DocumentList";
import { ArrowIcon, DetailIcon, EmbedderIcon, GoldenIcon, ScorerIcon } from "../components/Icons";
import { Upload } from "../components/Upload";
import { useSearchQuery } from "../state/searchQuery";
import {
  clearSelectedDocument,
  selectDocument,
  useSelectedDocument,
} from "../state/selectedDocument";
import type { Document, EvalRunSummary } from "../types";

function describeFailure(error: unknown): string {
  if (isApiError(error)) {
    return error.detail;
  }
  return error instanceof Error ? error.message : "Unknown error";
}

/** Deterministic UTC date (the API sends ISO-8601). */
function formatIngestDate(createdAt: string): string {
  const dateOnly = createdAt.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(dateOnly) ? dateOnly : createdAt;
}

/** Deterministic timestamp, matching the dashboard's run format. */
function formatRunTimestamp(value: string): string {
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value)
    ? value.slice(0, 19).replace("T", " ")
    : value;
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function timestampValue(run: EvalRunSummary): number {
  const parsed = Date.parse(run.created_at);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function newestFirst(runs: readonly EvalRunSummary[]): EvalRunSummary[] {
  return [...runs].sort(
    (first, second) => timestampValue(second) - timestampValue(first) || second.id - first.id,
  );
}

function filterDocuments(documents: readonly Document[], query: string): Document[] {
  const needle = query.trim().toLocaleLowerCase();
  if (needle === "") {
    return [...documents];
  }
  return documents.filter((document) => document.title.toLocaleLowerCase().includes(needle));
}

interface Remote<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/** A completed read, tagged with the document it belongs to. */
interface Loaded<T> {
  documentId: number | null;
  data: T | null;
  error: string | null;
}

/**
 * Read one selected-document endpoint and keep the last completed result keyed
 * to its document, so switching documents shows a loading state instead of the
 * previous document's data. Failures are caught and reported as text.
 *
 * The result is stored with its document id rather than reset synchronously in
 * the effect, so a document switch is a derivation (the tag no longer matches)
 * instead of a cascading render.
 */
function useRemote<T>(documentId: number | null, load: (id: number) => Promise<T>): Remote<T> {
  const [loaded, setLoaded] = useState<Loaded<T>>({ documentId: null, data: null, error: null });

  useEffect(() => {
    if (documentId === null) {
      return;
    }
    let active = true;
    load(documentId)
      .then((next) => {
        if (active) {
          setLoaded({ documentId, data: next, error: null });
        }
      })
      .catch((cause: unknown) => {
        if (active) {
          setLoaded({ documentId, data: null, error: describeFailure(cause) });
        }
      });
    return () => {
      active = false;
    };
  }, [documentId, load]);

  const isCurrent = documentId !== null && loaded.documentId === documentId;
  return {
    data: isCurrent ? loaded.data : null,
    error: isCurrent ? loaded.error : null,
    loading: documentId !== null && !isCurrent,
  };
}

interface CardProps {
  documentId: number | null;
}

function GoldenSetCard({ documentId }: CardProps): ReactElement {
  const remote = useRemote(documentId, getGoldenSet);

  return (
    <article className="glance-card" aria-busy={remote.loading}>
      <header className="glance-card__header">
        <span className="glance-card__chip" aria-hidden="true">
          <GoldenIcon />
        </span>
        <h4 className="glance-card__title">Golden set</h4>
      </header>
      {documentId === null ? (
        <p className="empty-state">Select a document to see its golden set.</p>
      ) : remote.error !== null ? (
        <p className="glance-card__error">Could not read the golden set: {remote.error}</p>
      ) : remote.loading || remote.data === null ? (
        <p className="muted">Loading the golden set…</p>
      ) : (
        <div className="glance-card__facts">
          <p className="glance-card__fact">Entries: {remote.data.entries.length}</p>
          <p className="glance-card__fact">Revision: {remote.data.revision}</p>
        </div>
      )}
    </article>
  );
}

function DocumentDetailCard({ documentId }: CardProps): ReactElement {
  const remote = useRemote(documentId, getDocument);

  return (
    <article className="glance-card" aria-busy={remote.loading}>
      <header className="glance-card__header">
        <span className="glance-card__chip" aria-hidden="true">
          <DetailIcon />
        </span>
        <h4 className="glance-card__title">Document detail</h4>
      </header>
      {documentId === null ? (
        <p className="empty-state">Select a document to see its details.</p>
      ) : remote.error !== null ? (
        <p className="glance-card__error">Could not read the document: {remote.error}</p>
      ) : remote.loading || remote.data === null ? (
        <p className="muted">Loading the document…</p>
      ) : (
        <div className="glance-card__facts">
          <p className="glance-card__fact">Pages: {remote.data.page_count}</p>
          <p className="glance-card__fact">Ingested {formatIngestDate(remote.data.created_at)}</p>
          <p className="glance-card__fact">Hash: {remote.data.content_hash.slice(0, 12)}</p>
        </div>
      )}
    </article>
  );
}

function EvalSummary({ documentId }: CardProps): ReactElement {
  const remote = useRemote(documentId, listEvalRuns);
  const runs = remote.data === null ? [] : newestFirst(remote.data);
  const latest = runs.length > 0 ? runs[0] : null;

  return (
    <>
      <section
        className="side-card"
        aria-labelledby="eval-summary-heading"
        aria-busy={remote.loading}
      >
        <header className="side-card__header">
          <h3 className="side-card__label" id="eval-summary-heading">
            Latest eval run
          </h3>
        </header>
        {documentId === null ? (
          <p className="empty-state">Select a document to see its eval runs.</p>
        ) : remote.error !== null ? (
          <p className="side-card__error">Could not load the eval history: {remote.error}</p>
        ) : remote.loading || remote.data === null ? (
          <p className="muted">Loading the eval history…</p>
        ) : latest === null ? (
          <div className="side-card__empty">
            <p className="empty-state">No eval runs yet</p>
            <a className="text-link" href="/evals">
              Open the Eval dashboard
            </a>
          </div>
        ) : (
          <>
            <dl className="metric-pair">
              <div className="metric-block">
                <dt className="metric-block__label">Retrieval hit rate</dt>
                <dd className="metric-block__value">{formatPercent(latest.hit_rate)}</dd>
              </div>
              <div className="metric-block">
                <dt className="metric-block__label">Answer faithfulness</dt>
                <dd className="metric-block__value">{formatPercent(latest.faithfulness)}</dd>
              </div>
            </dl>
            <p className="side-card__meta">
              k = {latest.k} · started{" "}
              <time dateTime={latest.created_at}>{formatRunTimestamp(latest.created_at)}</time>
            </p>
          </>
        )}
      </section>

      {runs.length > 0 ? (
        <section className="side-card side-card--runs" aria-labelledby="recent-runs-heading">
          <div className="section-heading">
            <h3 className="section-heading__title" id="recent-runs-heading">
              Recent eval runs
            </h3>
          </div>
          <div className="run-stack">
            {runs.slice(0, 2).map((run) => (
              <article className="run-summary" key={run.id}>
                <div className="pill-row">
                  <span className="pill">k = {run.k}</span>
                  <span className={run.flagged ? "pill pill--flagged" : "pill"}>
                    {run.flagged ? "Not comparable" : "Comparable"}
                  </span>
                </div>
                <div className="run-summary__title-row">
                  <h4 className="run-summary__title">Run #{run.id}</h4>
                  <p className="run-summary__hit">Hit rate {formatPercent(run.hit_rate)}</p>
                </div>
                <p className="run-summary__secondary">
                  Faithfulness {formatPercent(run.faithfulness)} · started{" "}
                  {formatRunTimestamp(run.created_at)}
                </p>
                <p className="run-summary__meta">
                  <span>
                    <EmbedderIcon className="run-summary__icon" />
                    {run.embedder_id}
                  </span>
                  <span>
                    <ScorerIcon className="run-summary__icon" />
                    {run.scorer_id}
                  </span>
                </p>
                <div className="run-summary__footer">
                  <a className="text-link" href="/evals">
                    Open the Eval dashboard
                    <ArrowIcon className="text-link__icon" />
                  </a>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}

/** Abstract palette-tone shapes; decorative and not from the reference. */
function HeroArt(): ReactElement {
  return (
    <svg className="hero__art-svg" viewBox="0 0 250 150" aria-hidden="true" focusable="false">
      <circle cx="196" cy="54" r="42" fill="var(--color-accent-secondary)" opacity="0.16" />
      <rect
        x="34"
        y="48"
        width="80"
        height="80"
        rx="22"
        fill="var(--color-accent)"
        opacity="0.12"
        transform="rotate(-8 74 88)"
      />
      <rect
        x="120"
        y="28"
        width="96"
        height="96"
        rx="28"
        fill="var(--color-accent-secondary)"
        opacity="0.1"
        transform="rotate(10 168 76)"
      />
      <circle cx="74" cy="44" r="18" fill="var(--color-accent)" opacity="0.22" />
      <path
        d="M40 118c26-22 62-22 88 0"
        stroke="var(--color-accent)"
        strokeWidth="6"
        strokeLinecap="round"
        fill="none"
        opacity="0.35"
      />
    </svg>
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
  const visibleDocuments = documents === null ? [] : filterDocuments(documents, searchQuery);

  return (
    <section className="page" aria-labelledby="library-heading">
      <div className="library-grid">
        <div className="library-main">
          <section className="hero">
            <div className="hero__copy">
              <h2 className="hero__kicker" id="library-heading">
                Library
              </h2>
              <p className="hero__headline">
                Local-first document Q&amp;A with page-cited answers and evaluation metrics.
              </p>
              <p className="hero__lede">
                Upload a PDF, then pick the one document you want to question.
              </p>
              <Upload existingDocuments={documents ?? []} onUploaded={refresh} />
            </div>
            <div className="hero__art">
              <HeroArt />
            </div>
          </section>

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
              documents={visibleDocuments}
              isFiltered={searchQuery.trim() !== ""}
              selectedDocumentId={selectedDocument?.id ?? null}
              onSelect={selectDocument}
              onDelete={handleDelete}
            />
          ) : null}

          <section className="glance" aria-labelledby="selected-document-heading">
            <div className="section-heading">
              <h3 className="section-heading__title" id="selected-document-heading">
                Selected document
              </h3>
            </div>
            <div className="glance-grid">
              <GoldenSetCard documentId={selectedDocument?.id ?? null} />
              <DocumentDetailCard documentId={selectedDocument?.id ?? null} />
            </div>
          </section>
        </div>

        <aside className="library-side" aria-label="Evaluation summary">
          <EvalSummary documentId={selectedDocument?.id ?? null} />
        </aside>
      </div>
    </section>
  );
}
