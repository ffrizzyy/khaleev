/**
 * The eval run history (F6, AC6, AC10): every persisted run, newest first.
 *
 * The backend already returns history newest first, but the list sorts on the
 * `(created_at, id)` pair it actually renders, so a reordered or equal-timestamp
 * response can never make the visible order disagree with the timestamp column.
 * Each row is an {@link EvalRunCard} compared against the newest run, which is
 * the same reference the backend's `flagged` field was computed from.
 */

import { useId } from "react";
import type { ReactElement } from "react";

import type { EvalRunDetail, EvalRunSummary } from "../types";
import { EvalRunCard } from "./EvalRunCard";

export interface EvalHistoryListProps {
  runs: readonly EvalRunSummary[];
  /** Loads per-entry results for an expanded row; defaults to the real API. */
  loadDetail?: (runId: number) => Promise<EvalRunDetail>;
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

export function EvalHistoryList({ runs, loadDetail }: EvalHistoryListProps): ReactElement {
  const headingId = useId();
  const ordered = newestFirst(runs);
  const reference = ordered[0];

  return (
    <section aria-labelledby={headingId}>
      <h3 id={headingId}>Run history</h3>
      {ordered.length === 0 ? (
        <p>No evaluation runs yet.</p>
      ) : (
        <>
          <p>
            Newest first. Each run is compared with the latest run&apos;s persisted configuration,
            not with live settings.
          </p>
          <ol>
            {ordered.map((run) => (
              <li key={run.id}>
                <EvalRunCard run={run} reference={reference} loadDetail={loadDetail} />
              </li>
            ))}
          </ol>
        </>
      )}
    </section>
  );
}
