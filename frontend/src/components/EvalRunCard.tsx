/**
 * One eval run as R1's stacked card (T24).
 *
 * The card follows the reference's anatomy without copying its content: a row
 * of two tag pills (`k = 5` and `Comparable` / `Not comparable`), a title with
 * the hit rate right-aligned, a muted secondary line, a meta row of two
 * icon-plus-text items read from the persisted run, and a footer action row
 * holding the per-entry disclosure.
 *
 * Comparability is stated in words, never by hue alone: the flag is a pill with
 * its own text and border, and the persisted difference that made the run
 * incomparable is spelled out in its own paragraph. Both metrics keep four
 * decimals plus a percentage, and the k a run used is named beside them, because
 * hit rates are only comparable at the same k.
 *
 * Per-entry results are loaded on demand from `GET /api/evals/{run_id}` (AC5)
 * and live behind a native `<button>` with `aria-expanded`/`aria-controls`, so
 * the disclosure is operable with Enter or Space as well as a pointer. The
 * controlled container is always in the DOM (hidden while collapsed), so the
 * `aria-controls` idref always resolves.
 */

import { useId, useState } from "react";
import type { ReactElement } from "react";

import { isApiError } from "../api/client";
import { getEvalRun } from "../api/evals";
import type { EvalRunDetail, EvalRunSummary } from "../types";
import { EmbedderIcon, ScorerIcon } from "./Icons";

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
    <article
      className={run.flagged ? "run-card run-card--flagged" : "run-card"}
      aria-labelledby={titleId}
    >
      <div className="pill-row">
        <span className="pill">k = {run.k}</span>
        <span className={run.flagged ? "pill pill--flagged" : "pill"}>
          {run.flagged ? "Not comparable" : "Comparable"}
        </span>
      </div>

      <div className="run-card__title-row">
        <h4 className="run-card__title" id={titleId}>
          Run #{run.id}
        </h4>
        <p className="run-card__hit">
          <span className="run-card__hit-label">Hit rate @ k={run.k}</span>
          <span className="run-card__hit-value">{formatMetric(run.hit_rate)}</span>
        </p>
      </div>

      <p className="run-card__secondary">
        Faithfulness <span className="run-card__metric">{formatMetric(run.faithfulness)}</span>{" "}
        &middot; started <time dateTime={run.created_at}>{formatRunTimestamp(run.created_at)}</time>
      </p>

      <p className="run-card__meta">
        <span>
          <EmbedderIcon className="run-card__icon" />
          {run.embedder_id}
        </span>
        <span>
          <ScorerIcon className="run-card__icon" />
          {run.scorer_id}
        </span>
      </p>

      {run.flagged ? (
        <p className="run-card__note run-card__note--flagged">{describeDifferences(run, latest)}</p>
      ) : (
        <p className="run-card__note">
          Shares k, embedder, scorer and golden-set revision with the latest run.
        </p>
      )}

      <div className="run-card__footer">
        <button
          className="button"
          type="button"
          aria-expanded={expanded}
          aria-controls={detailId}
          onClick={() => void toggleDetails()}
        >
          {expanded
            ? `Hide per-entry results for run ${run.id}`
            : `Show per-entry results for run ${run.id}`}
        </button>
      </div>

      <div className="run-card__detail" id={detailId} hidden={!expanded}>
        {expanded ? (
          <>
            {loadingDetail ? (
              <p className="status" role="status">
                Loading per-entry results for run {run.id}…
              </p>
            ) : null}
            {detailError !== null ? (
              <p className="alert" role="alert">
                {detailError}
              </p>
            ) : null}
            {detail !== null ? (
              <section className="entries" aria-label={`Per-entry results for run ${run.id}`}>
                {detail.entries.length === 0 ? (
                  <p className="empty-state">This run has no per-entry results.</p>
                ) : (
                  <ul className="entries__list">
                    {detail.entries.map((entry) => (
                      <li className="entry" key={entry.golden_index}>
                        <h5 className="entry__title">Golden index {entry.golden_index}</h5>
                        <p className="entry__meta">
                          <strong>{entry.hit ? "Hit" : "Miss"}</strong> —{" "}
                          {entry.hit
                            ? "at least one retrieved chunk was on an expected page"
                            : "no retrieved chunk was on an expected page"}{" "}
                          at k={detail.k}.
                        </p>
                        <p className="entry__meta">
                          Claims: {entry.claims}; supported claims: {entry.supported_claims};
                          per-entry faithfulness: {formatMetric(entry.faithfulness)}.
                        </p>
                        <blockquote className="entry__quote">
                          <p>{entry.answer}</p>
                        </blockquote>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            ) : null}
          </>
        ) : null}
      </div>
    </article>
  );
}
