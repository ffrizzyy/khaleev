/**
 * The eval dashboard (F6, AC6, AC10): run an evaluation for the selected
 * document, read the latest run's two metrics, and compare every past run.
 *
 * The page is the only stateful eval component; the cards, history list and
 * golden set view stay presentational. A keyed inner panel owns the per-document
 * state, so switching documents remounts it instead of briefly showing the
 * previous document's history or golden set.
 *
 * Three guarantees are encoded here:
 *
 * * With no document selected the page explains how to pick one and fires no
 *   request at all.
 * * A run is triggered with the chosen `k`, then the returned run is inserted
 *   immediately and the history is re-fetched, so the new metrics appear without
 *   a manual refresh.
 * * A failed run or golden-set load is rendered as text with the API's own
 *   detail (the 422 empty-set message included) plus the next step, never as an
 *   unhandled rejection or a blank panel.
 *
 * A fourth rule is the stale selection (Locked intent #17): the persisted id can
 * outlive its document, so the page re-checks it on mount against the list the
 * Library already loaded, and reads the API's own answer as the same case — a
 * 404 from the history route, or a 404 from the golden route whose detail names
 * the missing document. Both discard the selection silently and fall back to the
 * plain "No document selected" panel; every other failure keeps its error
 * notice. No new request is issued for any of it.
 */

import { useEffect, useId, useState } from "react";
import type { FormEvent, ReactElement } from "react";
import { Link } from "react-router-dom";

import { isApiError } from "../api/client";
import { getGoldenSet, listEvalRuns, startEval } from "../api/evals";
import { EvalHistoryList } from "../components/EvalHistoryList";
import { GoldenSetView } from "../components/GoldenSetView";
import type { GoldenSetViewError } from "../components/GoldenSetView";
import {
  clearSelectedDocument,
  reconcileSelection,
  useSelectedDocument,
} from "../state/selectedDocument";
import type { Document, EvalRunSummary, GoldenSet } from "../types";

function describeFailure(error: unknown): string {
  if (isApiError(error)) {
    return error.detail;
  }
  return error instanceof Error ? error.message : "Unknown error";
}

/**
 * True when a 404 means the document itself is gone.
 *
 * The golden route 404s both for an unknown document (stale selection — silent)
 * and for a missing golden-set file (a real, fixable condition that keeps its
 * own actionable message), so only a detail naming the missing document counts.
 * The API's wording is `document <id> does not exist`.
 */
function isMissingDocumentError(error: unknown): boolean {
  return (
    isApiError(error) &&
    error.status === 404 &&
    /document\s+\d+\s+does not exist/i.test(error.detail)
  );
}

function describeRunFailure(error: unknown): string {
  if (isApiError(error)) {
    switch (error.status) {
      case 404:
        return "The document or its golden-set file is missing. Re-upload the PDF or add a golden set, then try again.";
      case 422:
        return `Could not start the evaluation: ${error.detail} Add at least one valid entry to this document's golden set, then try again.`;
      case 503:
        return `The evaluation could not run: ${error.detail}`;
      default:
        return `Could not start the evaluation: ${error.detail}`;
    }
  }
  if (error instanceof Error) {
    return `Could not start the evaluation: ${error.message}`;
  }
  return "Could not start the evaluation.";
}

function formatMetric(value: number): string {
  return `${value.toFixed(4)} (${(value * 100).toFixed(2)}%)`;
}

function formatRunTimestamp(value: string): string {
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value)
    ? value.slice(0, 19).replace("T", " ")
    : value;
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

function NoDocument(): ReactElement {
  return (
    <section className="panel" aria-labelledby="no-document-heading">
      <h3 className="panel__title" id="no-document-heading">
        No document selected
      </h3>
      <p className="panel__text">
        Add an entry to a document&apos;s golden set and run an evaluation from here. First pick the
        document you want to evaluate.
      </p>
      <p className="page__action">
        <Link className="text-link" to="/">
          Go to the Library to pick a document
        </Link>
      </p>
    </section>
  );
}

interface EvaluationPanelProps {
  document: Document;
}

function EvaluationPanel({ document }: EvaluationPanelProps): ReactElement {
  const documentId = document.id;
  const kInputId = useId();
  const kHintId = useId();

  const [history, setHistory] = useState<EvalRunSummary[] | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [goldenSet, setGoldenSet] = useState<GoldenSet | null>(null);
  const [goldenError, setGoldenError] = useState<GoldenSetViewError | null>(null);
  const [kInput, setKInput] = useState("5");
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    let active = true;
    listEvalRuns(documentId)
      .then((next) => {
        if (active) {
          setHistoryError(null);
          setHistory(next);
        }
      })
      .catch((error: unknown) => {
        if (active) {
          if (isApiError(error) && error.status === 404) {
            // This route 404s only for an unknown document: the persisted
            // selection outlived it, so discard it and let the page fall back to
            // its plain "No document selected" state. Never an error notice.
            clearSelectedDocument();
            return;
          }
          setHistoryError(describeFailure(error));
        }
      });
    return () => {
      active = false;
    };
  }, [documentId, refreshToken]);

  useEffect(() => {
    let active = true;
    getGoldenSet(documentId)
      .then((next) => {
        if (active) {
          setGoldenError(null);
          setGoldenSet(next);
        }
      })
      .catch((error: unknown) => {
        if (!active) {
          return;
        }
        if (isMissingDocumentError(error)) {
          // The document is gone, so the golden set cannot exist either: the
          // same silent discard as above, never a golden-set error card.
          clearSelectedDocument();
          return;
        }
        setGoldenError({
          status: isApiError(error) ? error.status : null,
          message: describeFailure(error),
        });
      });
    return () => {
      active = false;
    };
  }, [documentId, refreshToken]);

  const orderedHistory = history === null ? [] : newestFirst(history);
  const latest = orderedHistory.length > 0 ? orderedHistory[0] : null;
  const loadingHistory = history === null && historyError === null;

  async function runEvaluation(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (running) {
      return;
    }
    const k = Number(kInput);
    if (!Number.isInteger(k) || k < 1) {
      setRunError("Enter a whole number for k (1 or more) before running the evaluation.");
      return;
    }

    setRunning(true);
    setRunError(null);
    try {
      const created = await startEval(documentId, k);
      const createdSummary: EvalRunSummary = {
        ...created,
        comparable: true,
        flagged: false,
      };
      setHistory((current) => [
        createdSummary,
        ...(current ?? []).filter((run) => run.id !== created.id),
      ]);
      setRefreshToken((token) => token + 1);
    } catch (error) {
      setRunError(describeRunFailure(error));
    } finally {
      setRunning(false);
    }
  }

  function retryLoad(): void {
    setHistoryError(null);
    setGoldenError(null);
    setRefreshToken((token) => token + 1);
  }

  return (
    <>
      <p className="eval-subject">Evaluating {document.title}.</p>

      <div className="page-grid page-grid--two">
        <div className="page-grid__main">
          {historyError !== null ? (
            <div className="notice" role="alert">
              <p className="notice__text">Could not load the evaluation history: {historyError}</p>
              <button className="button" type="button" onClick={retryLoad}>
                Retry loading the eval dashboard
              </button>
            </div>
          ) : null}

          {loadingHistory ? (
            <p className="status" role="status">
              Loading evaluation history…
            </p>
          ) : null}

          {history !== null && history.length === 0 ? (
            <section className="panel panel--empty" aria-labelledby="no-runs-heading">
              <h3 className="panel__title" id="no-runs-heading">
                No evaluation runs yet
              </h3>
              <p className="panel__text">
                To get a first run, add at least one entry to this document&apos;s golden-set JSON
                file (question, expected answer and at least one expected page), choose k above,
                then select Run evaluation.
              </p>
            </section>
          ) : null}

          {latest !== null ? (
            <section className="panel panel--latest" aria-labelledby="latest-run-heading">
              <div className="section-heading">
                <h3 className="panel__title" id="latest-run-heading">
                  Latest run
                </h3>
                <p className="latest-run__stamp">
                  Run #{latest.id}, started{" "}
                  <time dateTime={latest.created_at}>{formatRunTimestamp(latest.created_at)}</time>
                </p>
              </div>
              <dl className="metrics">
                <div className="metric">
                  <dt className="metric__label">Retrieval hit rate @ k={latest.k}</dt>
                  <dd className="metric__value">{formatMetric(latest.hit_rate)}</dd>
                </div>
                <div className="metric">
                  <dt className="metric__label">Answer faithfulness</dt>
                  <dd className="metric__value">{formatMetric(latest.faithfulness)}</dd>
                </div>
              </dl>
              <p className="latest-run__meta">
                These are the numbers every history row is compared with.
              </p>
            </section>
          ) : null}

          {history !== null && history.length > 0 ? <EvalHistoryList runs={history} /> : null}
        </div>

        <div className="page-grid__side">
          <section
            className="panel panel--run"
            aria-labelledby="run-eval-heading"
            aria-busy={running}
          >
            <h3 className="panel__title" id="run-eval-heading">
              Run an evaluation
            </h3>
            <form className="run-form" onSubmit={(event) => void runEvaluation(event)}>
              <label className="field__label" htmlFor={kInputId}>
                k
              </label>
              <input
                className="field__number"
                id={kInputId}
                type="number"
                min={1}
                step={1}
                inputMode="numeric"
                value={kInput}
                disabled={running}
                aria-describedby={kHintId}
                onChange={(event) => setKInput(event.currentTarget.value)}
              />
              <p className="field__hint" id={kHintId}>
                k is the number of retrieved chunks per question. The run records the k it used, so
                hit rates are only comparable at the same k.
              </p>
              <button className="button button--primary" type="submit" disabled={running}>
                Run evaluation
              </button>
            </form>
            {running ? (
              <p className="status" role="status">
                Running the evaluation…
              </p>
            ) : null}
            {runError !== null ? (
              <p className="alert" role="alert">
                {runError}
              </p>
            ) : null}
          </section>

          <GoldenSetView
            goldenSet={goldenSet}
            error={goldenError}
            loading={goldenSet === null && goldenError === null}
          />
        </div>
      </div>
    </>
  );
}

export function EvalDashboard(): ReactElement {
  const selected = useSelectedDocument();

  // The persisted id can outlive its document. Re-check it against the list the
  // Library already loaded, and drop to the plain empty state when it is gone.
  // No request is minted here (the page's request set is pinned by its tests);
  // a reload straight onto this page is covered by the API's own 404s above.
  useEffect(() => {
    reconcileSelection();
  }, []);

  return (
    <section className="page" aria-labelledby="evals-heading">
      <header className="page__header">
        <h2 className="page__title" id="evals-heading">
          Eval dashboard
        </h2>
        <p className="page__lede">
          Retrieval hit rate and answer faithfulness for each eval run, with history across runs.
        </p>
      </header>
      {selected === null ? (
        <NoDocument />
      ) : (
        <EvaluationPanel key={selected.id} document={selected} />
      )}
    </section>
  );
}
