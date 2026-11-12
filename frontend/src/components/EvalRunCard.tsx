/**
 * One eval run as the dashboard presents it (F6, AC6, AC10).
 *
 * The card always states the two metrics as text, so they are readable without
 * colour: `hit_rate@k` names the k the run used, and both values are shown to
 * four decimals plus a percentage. Comparability is not a silent styling hint:
 * a flagged run says "Not comparable" in words and, when the persisted config
 * exposes it, names the field that differs from the latest run.
 *
 * Per-entry results are loaded on demand from `GET /api/evals/{run_id}` (AC5)
 * and live behind a native `<button>` with `aria-expanded`/`aria-controls`, so
 * the disclosure is operable with Enter or Space as well as a pointer.
 */

import { useId, useState } from "react";
import type { ReactElement } from "react";

import { isApiError } from "../api/client";
import { getEvalRun } from "../api/evals";
import type { EvalRunDetail, EvalRunSummary } from "../types";

export interface EvalRunCardProps {
  run: EvalRunSummary;
  /** The latest run this one is compared against; defaults to the run itself. */
  reference?: EvalRunSummary;
  /** Loads per-entry results; defaults to the real `GET /api/evals/{id}`. */
  loadDetail?: (runId: number) => Promise<EvalRunDetail>;
}

/** The persisted value with four decimals and the same value as a percentage. */
function formatMetric(value: number): string {
  return `${value.toFixed(4)} (${(value * 100).toFixed(2)}%)`;
}

/** Deterministic UTC rendering of the API's ISO-8601 timestamp. */
function formatRunTimestamp(value: string): string {
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value)
    ? value.slice(0, 19).replace("T", " ")
    : value;
}

function describeFailure(error: unknown): string {
  if (isApiError(error)) {
    return error.detail;
  }
  return error instanceof Error ? error.message : "Unknown error";
}

function revisionOf(run: EvalRunSummary): string {
  const value = run.config.golden_set_revision;
  if (typeof value === "string") {
    return value;
  }
  return value === null || value === undefined ? "" : JSON.stringify(value);
}

interface FieldDifference {
  label: string;
  current: string;
  latest: string;
}

function describeDifferences(run: EvalRunSummary, latest: EvalRunSummary): string {
  const differences: FieldDifference[] = [
    { label: "k", current: String(run.k), latest: String(latest.k) },
    { label: "embedder", current: run.embedder_id, latest: latest.embedder_id },
    { label: "scorer", current: run.scorer_id, latest: latest.scorer_id },
    {
      label: "golden-set revision",
      current: revisionOf(run),
      latest: revisionOf(latest),
    },
  ].filter((field) => field.current !== field.latest);

  if (differences.length === 0) {
    return "The persisted run configuration differs from the latest run.";
  }

  return `${differences
    .map((field) => `${field.label} differs (this run: ${field.current}; latest: ${field.latest})`)
    .join("; ")}.`;
}

export function EvalRunCard({
  run,
  reference,
  loadDetail = getEvalRun,
}: EvalRunCardProps): ReactElement {
  const titleId = useId();
  const detailId = useId();
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState<EvalRunDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const latest = reference ?? run;

  async function toggleDetails(): Promise<void> {
    const next = !expanded;
    setExpanded(next);
    if (!next || detail !== null || loadingDetail) {
      return;
    }
    setLoadingDetail(true);
    setDetailError(null);
    try {
      setDetail(await loadDetail(run.id));
    } catch (error) {
      setDetailError(`Could not load the per-entry results: ${describeFailure(error)}`);
    } finally {
      setLoadingDetail(false);
    }
  }

  return (
    <article aria-labelledby={titleId}>
      <header>
        <h4 id={titleId}>Run #{run.id}</h4>
        <p>
          Started <time dateTime={run.created_at}>{formatRunTimestamp(run.created_at)}</time>
        </p>
        <p>k = {run.k}</p>
      </header>

      <dl>
        <div>
          <dt>Retrieval hit rate @ k={run.k}</dt>
          <dd>{formatMetric(run.hit_rate)}</dd>
        </div>
        <div>
          <dt>Answer faithfulness</dt>
          <dd>{formatMetric(run.faithfulness)}</dd>
        </div>
      </dl>

      {run.flagged ? (
        <div>
          <p>
            <strong>Not comparable</strong>
          </p>
          <p>{describeDifferences(run, latest)}</p>
        </div>
      ) : (
        <p>
          <strong>Comparable</strong> — this run shares k, embedder, scorer and golden-set revision
          with the latest run.
        </p>
      )}

      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={detailId}
        onClick={() => void toggleDetails()}
      >
        {expanded
          ? `Hide per-entry results for run ${run.id}`
          : `Show per-entry results for run ${run.id}`}
      </button>

      {expanded ? (
        <div id={detailId}>
          {loadingDetail ? <p role="status">Loading per-entry results for run {run.id}…</p> : null}
          {detailError !== null ? <p role="alert">{detailError}</p> : null}
          {detail !== null ? (
            <section aria-label={`Per-entry results for run ${run.id}`}>
              {detail.entries.length === 0 ? (
                <p>This run has no per-entry results.</p>
              ) : (
                <ul>
                  {detail.entries.map((entry) => (
                    <li key={entry.golden_index}>
                      <h5>Golden index {entry.golden_index}</h5>
                      <p>
                        <strong>{entry.hit ? "Hit" : "Miss"}</strong> —{" "}
                        {entry.hit
                          ? "at least one retrieved chunk was on an expected page"
                          : "no retrieved chunk was on an expected page"}{" "}
                        at k={detail.k}.
                      </p>
                      <p>
                        Claims: {entry.claims}; supported claims: {entry.supported_claims};
                        per-entry faithfulness: {formatMetric(entry.faithfulness)}.
                      </p>
                      <blockquote>
                        <p>{entry.answer}</p>
                      </blockquote>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
