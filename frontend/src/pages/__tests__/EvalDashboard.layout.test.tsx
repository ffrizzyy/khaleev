/**
 * Layout coverage for the T24 Eval dashboard: the two headline metrics, the
 * stacked run cards and the two-column placement of the run form and the
 * golden set.
 *
 * Structure, roles and text only — never a class name. Document order is what
 * makes the R1 columns stack correctly below 1280px, so the assertions compare
 * node positions; element kinds (span/paragraph/list item) are asserted where
 * the requirement is that a cue is text and a list stays a list of runs.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearSelectedDocument,
  getSelectedDocument,
  rememberDocuments,
  selectDocument,
} from "../../state/selectedDocument";
import type {
  Document,
  EvalRun,
  EvalRunDetail,
  EvalRunEntry,
  EvalRunSummary,
  GoldenSet,
} from "../../types";
import { EvalDashboard } from "../EvalDashboard";

const fetchMock = vi.fn<typeof fetch>();

const paper: Document = {
  id: 1,
  title: "Tax guide.pdf",
  page_count: 4,
  created_at: "2026-02-03T10:15:00Z",
};

/** A live document the app knows about; not the persisted Q&A target. */
const other: Document = {
  id: 2,
  title: "Other.pdf",
  page_count: 1,
  created_at: "2026-03-04T08:00:00Z",
};

const goldenSet: GoldenSet = {
  document_id: paper.id,
  revision: "rev-abc",
  entries: [
    {
      question: "What penalty applies to late filings?",
      expected_answer: "Late filings incur a flat 200 credit penalty per return.",
      expected_pages: [3],
    },
  ],
};

const baseConfig = {
  document_id: paper.id,
  k: 5,
  embedder_id: "all-MiniLM-L6-v2",
  generator: { kind: "ollama", model: "llama3.1:8b" },
  scorer_id: "nli-local",
  scorer_version: "1.0.0",
  golden_set_revision: "rev-abc",
};

function runSummary(overrides: Partial<EvalRunSummary> = {}): EvalRunSummary {
  return {
    id: 2,
    document_id: paper.id,
    created_at: "2026-05-02T10:00:00Z",
    k: 10,
    embedder_id: "all-MiniLM-L6-v2",
    scorer_id: "nli-local",
    hit_rate: 0.6667,
    faithfulness: 0.5,
    config: { ...baseConfig, k: 10 },
    comparable: true,
    flagged: false,
    ...overrides,
  };
}

const entries: EvalRunEntry[] = [
  {
    golden_index: 0,
    hit: true,
    answer: "Late filings incur a flat 200 credit penalty per return.",
    claims: 2,
    supported_claims: 1,
    faithfulness: 0.5,
  },
];

function runDetail(run: EvalRun): EvalRunDetail {
  return { ...run, entries };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installApi(runs: readonly EvalRunSummary[]): void {
  fetchMock.mockImplementation(async (input) => {
    const url = String(input);
    if (url === `/api/documents/${paper.id}/evals`) {
      return jsonResponse(runs);
    }
    if (url === `/api/documents/${paper.id}/golden`) {
      return jsonResponse(goldenSet);
    }
    const detailMatch = /^\/api\/evals\/(\d+)$/.exec(url);
    if (detailMatch !== null) {
      const run = runs.find((candidate) => candidate.id === Number(detailMatch[1]));
      if (run !== undefined) {
        return jsonResponse(runDetail(run));
      }
    }
    throw new Error(`Unexpected request: ${url}`);
  });
}

/** True when `first` comes before `second` in document order. */
function precedes(first: Element, second: Element): boolean {
  const position = first.compareDocumentPosition(second);
  return (position & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

function renderDashboard() {
  render(
    <MemoryRouter>
      <EvalDashboard />
    </MemoryRouter>,
  );
}

async function findHistory() {
  return screen.findByRole("region", { name: "Run history" });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  clearSelectedDocument();
  sessionStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Eval dashboard layout", () => {
  it("orders the metrics and the history before the run form and the golden set", async () => {
    const latest = runSummary({ id: 2, k: 10, config: { ...baseConfig, k: 10 } });
    const older = runSummary({ id: 1, k: 5, flagged: true, comparable: false });
    selectDocument(paper);
    installApi([older, latest]);
    renderDashboard();

    const latestRegion = await screen.findByRole("region", { name: "Latest run" });
    const history = await findHistory();
    const runForm = screen.getByRole("region", { name: "Run an evaluation" });
    const golden = await screen.findByRole("region", { name: "Golden set" });

    // Left column: metrics, then history. Right column: the run form, then the
    // golden set. DOM order is what the responsive stacking follows.
    expect(precedes(latestRegion, history)).toBe(true);
    expect(precedes(history, runForm)).toBe(true);
    expect(precedes(runForm, golden)).toBe(true);
  });

  it("presents both metrics as labelled values of one definition list in the latest run", async () => {
    selectDocument(paper);
    installApi([runSummary({ id: 2, k: 10, config: { ...baseConfig, k: 10 } })]);
    renderDashboard();

    const latest = await screen.findByRole("region", { name: "Latest run" });
    expect(within(latest).getByText("Retrieval hit rate @ k=10")).toBeInTheDocument();
    expect(within(latest).getByText("0.6667 (66.67%)").closest("dl")).not.toBeNull();
    expect(within(latest).getByText("Answer faithfulness")).toBeInTheDocument();
    expect(within(latest).getByText("0.5000 (50.00%)").closest("dl")).not.toBeNull();
  });

  it("keeps two runs in the history list while each run carries tag pills and a meta row", async () => {
    const latest = runSummary({ id: 2, k: 10, config: { ...baseConfig, k: 10 } });
    const older = runSummary({ id: 1, k: 5, flagged: true, comparable: false });
    selectDocument(paper);
    installApi([latest, older]);
    renderDashboard();

    const history = await findHistory();
    const rows = within(history).getAllByRole("listitem");
    expect(rows).toHaveLength(2);

    const kPill = within(rows[0]).getByText("k = 10");
    expect(kPill.tagName).toBe("SPAN");
    expect(kPill.closest("li")).toBe(rows[0]);

    const comparability = within(rows[0]).getByText("Comparable");
    expect(comparability.tagName).toBe("SPAN");
    expect(comparability.closest("li")).toBe(rows[0]);

    // The meta row and the footer action are spans/paragraphs, never list items,
    // so the history region keeps exactly one list item per run.
    expect(within(rows[0]).getByText("all-MiniLM-L6-v2").tagName).toBe("SPAN");
    expect(within(rows[0]).getByText("nli-local").tagName).toBe("SPAN");
    expect(
      within(rows[0])
        .getByRole("button", { name: /per-entry results/i })
        .closest("li"),
    ).toBe(rows[0]);
    expect(within(rows[0]).getByRole("heading", { name: "Run #2" })).toBeInTheDocument();
    expect(within(rows[0]).getByText("2026-05-02 10:00:00")).toHaveAttribute(
      "datetime",
      "2026-05-02T10:00:00Z",
    );
  });

  it("states a non-comparable run in words as a separate explanation, not colour alone", async () => {
    const latest = runSummary({ id: 2, k: 10, config: { ...baseConfig, k: 10 } });
    const older = runSummary({
      id: 1,
      k: 5,
      created_at: "2026-05-01T10:00:00Z",
      flagged: true,
      comparable: false,
    });
    selectDocument(paper);
    installApi([latest, older]);
    renderDashboard();

    const rows = within(await findHistory()).getAllByRole("listitem");
    const label = within(rows[1]).getByText("Not comparable");
    const explanation = within(rows[1]).getByText("k differs (this run: 5; latest: 10).");

    // Two distinct text nodes: the label says what the state is, the paragraph
    // says why. Neither depends on the reader perceiving a hue.
    expect(label).not.toBe(explanation);
    expect(label.tagName).toBe("SPAN");
    expect(explanation.tagName).toBe("P");
    expect(explanation.textContent).toBe("k differs (this run: 5; latest: 10).");
  });

  it("keeps the disclosure a button whose aria-controls resolves to the detail card", async () => {
    const run = runSummary({ id: 2 });
    selectDocument(paper);
    installApi([run]);
    const user = userEvent.setup();
    renderDashboard();

    const toggle = await screen.findByRole("button", {
      name: `Show per-entry results for run ${run.id}`,
    });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    const controls = toggle.getAttribute("aria-controls");
    expect(controls).not.toBeNull();
    const detail = document.getElementById(controls as string);
    expect(detail).not.toBeNull();
    expect(detail).toHaveAttribute("hidden");

    toggle.focus();
    await user.keyboard("{Enter}");

    await waitFor(() => expect(toggle).toHaveAttribute("aria-expanded", "true"));
    expect(toggle).toHaveAccessibleName(`Hide per-entry results for run ${run.id}`);
    await waitFor(() => expect(detail).not.toHaveAttribute("hidden"));
    expect(await screen.findByRole("heading", { name: "Golden index 0" })).toBeInTheDocument();
  });

  it("keeps the k input labelled and defaulted in the run card", async () => {
    selectDocument(paper);
    installApi([runSummary()]);
    renderDashboard();

    expect(await screen.findByLabelText("k")).toHaveValue(5);
    expect(screen.getByRole("button", { name: "Run evaluation" })).toBeInTheDocument();
  });

  it("states the no-document empty state once, with the Library link", () => {
    renderDashboard();

    const heading = screen.getByRole("heading", { name: "No document selected" });
    const panel = heading.closest("section");
    expect(panel).not.toBeNull();

    // One short sentence, then the existing link — no second sentence saying
    // the same thing again.
    expect(
      within(panel as HTMLElement).getByText(
        "Add an entry to a document's golden set and run an evaluation from here.",
      ),
    ).toBeInTheDocument();
    expect(
      within(panel as HTMLElement).queryByText(/first pick the document you want to evaluate/i),
    ).not.toBeInTheDocument();
    expect(within(panel as HTMLElement).getByRole("link", { name: /library/i })).toHaveAttribute(
      "href",
      "/",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("discards a persisted selection the recorded list no longer contains", async () => {
    rememberDocuments([other]);
    selectDocument(paper);
    // The document is gone, so both of the page's own requests say so.
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (
        url === `/api/documents/${paper.id}/evals` ||
        url === `/api/documents/${paper.id}/golden`
      ) {
        return jsonResponse({ detail: `document ${paper.id} does not exist` }, 404);
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    renderDashboard();

    expect(await screen.findByText("No document selected")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /library/i })).toHaveAttribute("href", "/");
    // A deleted document is not an error, and its id is never spelled out.
    expect(screen.queryByText(/does not exist/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Latest run" })).not.toBeInTheDocument();
  });

  it("reads a 404 from the eval history as the document being gone, not as an error", async () => {
    selectDocument(paper);
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (
        url === `/api/documents/${paper.id}/evals` ||
        url === `/api/documents/${paper.id}/golden`
      ) {
        return jsonResponse({ detail: `document ${paper.id} does not exist` }, 404);
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    renderDashboard();

    expect(await screen.findByText("No document selected")).toBeInTheDocument();
    expect(screen.queryByText(/document 1 does not exist/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/could not load/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("still reports a genuine 500 from the eval history with its retry affordance", async () => {
    selectDocument(paper);
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === `/api/documents/${paper.id}/evals`) {
        return jsonResponse({ detail: "Database unavailable" }, 500);
      }
      if (url === `/api/documents/${paper.id}/golden`) {
        return jsonResponse(goldenSet);
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    renderDashboard();

    expect(
      await screen.findByText(/could not load the evaluation history: database unavailable/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry loading the eval dashboard" })).toBeEnabled();
    expect(screen.queryByText("No document selected")).not.toBeInTheDocument();
  });

  it("keeps the missing golden-set file message when the document itself still exists", async () => {
    selectDocument(paper);
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === `/api/documents/${paper.id}/evals`) {
        return jsonResponse([]);
      }
      if (url === `/api/documents/${paper.id}/golden`) {
        return jsonResponse(
          { detail: `golden set for document ${paper.id} not found at /data/golden/1.json` },
          404,
        );
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    renderDashboard();

    expect(await screen.findByText(/golden set for document 1 not found/i)).toBeInTheDocument();
    expect(screen.getByText(/the golden-set file is missing/i)).toBeInTheDocument();
    expect(screen.queryByText("No document selected")).not.toBeInTheDocument();
    expect(getSelectedDocument()?.id).toBe(paper.id);
  });
});
