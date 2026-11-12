/**
 * The document's golden set, read-only in the UI (F4, AC4).
 *
 * Three states get an explicit explanation rather than a blank panel: loading,
 * a load failure (the API's 422 for an empty or invalid set, or the 404 for a
 * missing file, is surfaced verbatim alongside what to add), and a set that has
 * no entries. A golden set is hand-edited JSON on disk in v1, so the guidance
 * names the file's expected entry fields instead of pretending there is an
 * editor here.
 */

import { useId } from "react";
import type { ReactElement } from "react";

import type { GoldenSet } from "../types";

export interface GoldenSetViewError {
  status: number | null;
  message: string;
}

export interface GoldenSetViewProps {
  goldenSet: GoldenSet | null;
  error?: GoldenSetViewError | null;
  loading?: boolean;
}

function pagesLabel(pages: readonly number[]): string {
  return pages.length === 1 ? `page ${pages[0]}` : `pages ${pages.join(", ")}`;
}

const ADD_ENTRY_GUIDANCE =
  "Add at least one valid entry to this document's golden-set JSON file " +
  "(question, expected answer and at least one expected page), then reload the dashboard.";

export function GoldenSetView({
  goldenSet,
  error = null,
  loading = false,
}: GoldenSetViewProps): ReactElement {
  const headingId = useId();

  if (loading) {
    return (
      <section aria-labelledby={headingId}>
        <h3 id={headingId}>Golden set</h3>
        <p role="status">Loading the golden set…</p>
      </section>
    );
  }

  if (error !== null) {
    const guidance =
      error.status === 404
        ? "The golden-set file is missing. Re-upload the PDF to recreate it, then add at least one valid entry."
        : ADD_ENTRY_GUIDANCE;
    return (
      <section aria-labelledby={headingId}>
        <h3 id={headingId}>Golden set</h3>
        <div role="alert">
          <p>Could not load the golden set: {error.message}</p>
          <p>{guidance}</p>
        </div>
      </section>
    );
  }

  if (goldenSet === null) {
    return (
      <section aria-labelledby={headingId}>
        <h3 id={headingId}>Golden set</h3>
        <p>No golden set is available for this document.</p>
      </section>
    );
  }

  return (
    <section aria-labelledby={headingId}>
      <h3 id={headingId}>Golden set</h3>
      <p>
        Read-only. This curated set is what every evaluation scores against. Revision{" "}
        <code>{goldenSet.revision}</code>.
      </p>
      {goldenSet.entries.length === 0 ? (
        <p>No golden entries yet. {ADD_ENTRY_GUIDANCE}</p>
      ) : (
        <ol>
          {goldenSet.entries.map((entry, index) => (
            <li key={index}>
              <h4>
                Entry {index + 1}: {entry.question}
              </h4>
              <p>Expected answer: {entry.expected_answer}</p>
              <p>Expected {pagesLabel(entry.expected_pages)}.</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
