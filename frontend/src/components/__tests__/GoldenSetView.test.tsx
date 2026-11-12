import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { GoldenSet } from "../../types";
import { GoldenSetView } from "../GoldenSetView";

const goldenSet: GoldenSet = {
  document_id: 1,
  revision: "rev-abc123",
  entries: [
    {
      question: "What penalty applies to late filings?",
      expected_answer: "Late filings incur a flat 200 credit penalty per return.",
      expected_pages: [3, 4],
    },
    {
      question: "How long do refunds take to process?",
      expected_answer: "Refunds are processed within ten business days.",
      expected_pages: [1],
    },
  ],
};

describe("GoldenSetView", () => {
  it("shows the golden set read-only with questions, expected answers and pages", () => {
    render(<GoldenSetView goldenSet={goldenSet} />);

    expect(screen.getByRole("heading", { name: "Golden set" })).toBeInTheDocument();
    expect(screen.getByText(/read-only/i)).toBeInTheDocument();
    expect(screen.getByText("rev-abc123")).toBeInTheDocument();

    const entries = within(screen.getByRole("region", { name: "Golden set" })).getAllByRole(
      "listitem",
    );
    expect(entries).toHaveLength(2);
    expect(
      within(entries[0]).getByText(/What penalty applies to late filings\?/),
    ).toBeInTheDocument();
    expect(
      within(entries[0]).getByText(/Late filings incur a flat 200 credit penalty per return\./),
    ).toBeInTheDocument();
    expect(within(entries[0]).getByText(/3, 4/)).toBeInTheDocument();
    expect(
      within(entries[1]).getByText(/How long do refunds take to process\?/),
    ).toBeInTheDocument();
    expect(within(entries[1]).getByText(/1/)).toBeInTheDocument();
  });

  it("surfaces a 422 message with guidance when the golden set is missing or empty", () => {
    render(
      <GoldenSetView
        goldenSet={null}
        error={{
          status: 422,
          message: "The golden set is empty; add at least one entry.",
        }}
      />,
    );

    expect(
      screen.getByText(/the golden set is empty; add at least one entry\./i),
    ).toBeInTheDocument();
    expect(screen.getByText(/add at least one valid entry/i)).toBeInTheDocument();
  });

  it("explains what to add when the set has no entries yet", () => {
    render(<GoldenSetView goldenSet={{ ...goldenSet, entries: [] }} />);

    expect(screen.getByText(/no golden entries yet/i)).toBeInTheDocument();
    expect(screen.getByText(/add at least one valid entry/i)).toBeInTheDocument();
  });

  it("reports that the golden set is loading", () => {
    render(<GoldenSetView goldenSet={null} loading />);

    expect(screen.getByRole("status")).toHaveTextContent(/loading the golden set/i);
  });
});
