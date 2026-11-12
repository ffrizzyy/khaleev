import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EvalRunSummary } from "../../types";
import { EvalHistoryList } from "../EvalHistoryList";

const fetchMock = vi.fn<typeof fetch>();

const baseConfig = {
  document_id: 1,
  k: 5,
  embedder_id: "all-MiniLM-L6-v2",
  scorer_id: "nli-local",
  scorer_version: "1.0.0",
  golden_set_revision: "rev-abc",
};

function summary(overrides: Partial<EvalRunSummary> = {}): EvalRunSummary {
  return {
    id: 1,
    document_id: 1,
    created_at: "2026-05-01T10:00:00Z",
    k: 5,
    embedder_id: "all-MiniLM-L6-v2",
    scorer_id: "nli-local",
    hit_rate: 0.6667,
    faithfulness: 0.5,
    config: { ...baseConfig },
    comparable: true,
    flagged: false,
    ...overrides,
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("EvalHistoryList", () => {
  it("renders every run newest first with time, k and both metrics", () => {
    const latest = summary({
      id: 2,
      created_at: "2026-05-02T10:00:00Z",
      k: 10,
      config: { ...baseConfig, k: 10 },
      hit_rate: 0.75,
      faithfulness: 1.0,
    });
    const older = summary({ id: 1, created_at: "2026-05-01T10:00:00Z" });

    render(<EvalHistoryList runs={[older, latest]} />);

    const history = screen.getByRole("region", { name: "Run history" });
    const rows = within(history).getAllByRole("listitem");
    expect(rows).toHaveLength(2);

    expect(within(rows[0]).getByText("Run #2")).toBeInTheDocument();
    expect(within(rows[0]).getByText("k = 10")).toBeInTheDocument();
    expect(within(rows[0]).getByText("2026-05-02 10:00:00")).toHaveAttribute(
      "datetime",
      "2026-05-02T10:00:00Z",
    );
    expect(within(rows[0]).getByText("0.7500 (75.00%)")).toBeInTheDocument();
    expect(within(rows[0]).getByText("1.0000 (100.00%)")).toBeInTheDocument();

    expect(within(rows[1]).getByText("Run #1")).toBeInTheDocument();
    expect(within(rows[1]).getByText("k = 5")).toBeInTheDocument();
    expect(within(rows[1]).getByText("0.6667 (66.67%)")).toBeInTheDocument();
    expect(within(rows[1]).getByText("0.5000 (50.00%)")).toBeInTheDocument();

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("marks a run as not comparable in text and names the field that differs", () => {
    const latest = summary({ id: 2, k: 10, config: { ...baseConfig, k: 10 } });
    const older = summary({
      id: 1,
      k: 5,
      comparable: false,
      flagged: true,
    });

    render(<EvalHistoryList runs={[latest, older]} />);

    const rows = screen.getAllByRole("listitem");
    expect(within(rows[0]).getByText("Comparable")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Not comparable")).toBeInTheDocument();
    expect(within(rows[1]).getByText("k differs (this run: 5; latest: 10).")).toBeInTheDocument();
  });

  it("explains that a flagged run's persisted configuration differs when no single field can be named", () => {
    const latest = summary({ id: 2 });
    const older = summary({
      id: 1,
      comparable: false,
      flagged: true,
      config: { ...baseConfig },
    });

    render(<EvalHistoryList runs={[latest, older]} />);

    // Same displayed fields but the backend flagged it: the fallback explanation
    // still tells the user not to compare the numbers directly.
    expect(screen.getByText("Not comparable")).toBeInTheDocument();
    expect(
      screen.getByText("The persisted run configuration differs from the latest run."),
    ).toBeInTheDocument();
  });

  it("renders a readable empty message instead of an empty list", () => {
    render(<EvalHistoryList runs={[]} />);

    expect(screen.getByText(/no evaluation runs yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });
});
