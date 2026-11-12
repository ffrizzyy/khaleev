import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSelectedDocument, selectDocument } from "../../state/selectedDocument";
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

const goldenSet: GoldenSet = {
  document_id: paper.id,
  revision: "rev-abc",
  entries: [
    {
      question: "What penalty applies to late filings?",
      expected_answer: "Late filings incur a flat 200 credit penalty per return.",
      expected_pages: [3],
    },
    {
      question: "How long do refunds take to process?",
      expected_answer: "Refunds are processed within ten business days.",
      expected_pages: [1],
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

const entries: EvalRunEntry[] = [
  {
    golden_index: 0,
    hit: true,
    answer: "Late filings incur a flat 200 credit penalty per return.",
    claims: 2,
    supported_claims: 1,
    faithfulness: 0.5,
  },
  {
    golden_index: 1,
    hit: false,
    answer: "Refunds take ten days.",
    claims: 1,
    supported_claims: 0,
    faithfulness: 0.0,
  },
];

function runDetail(run: EvalRun, overrides: Partial<EvalRunDetail> = {}): EvalRunDetail {
  return { ...run, entries, ...overrides };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderDashboard() {
  render(
    <MemoryRouter>
      <EvalDashboard />
    </MemoryRouter>,
  );
}

function requestedUrls(): string[] {
  return fetchMock.mock.calls.map(([input]) => String(input));
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

describe("EvalDashboard", () => {
  it("explains how to pick a document and fires no request when none is selected", () => {
    renderDashboard();

    expect(screen.getByRole("heading", { name: "Eval dashboard" })).toBeInTheDocument();
    expect(screen.getByText(/no document selected/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /library/i })).toHaveAttribute("href", "/");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("explains how to get a first run when the document has no history", async () => {
    selectDocument(paper);
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === `/api/documents/${paper.id}/evals`) {
        return jsonResponse([]);
      }
      if (url === `/api/documents/${paper.id}/golden`) {
        return jsonResponse(goldenSet);
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    renderDashboard();

    expect(await screen.findByText(/no evaluation runs yet/i)).toBeInTheDocument();
    expect(screen.getByText(/to get a first run/i)).toBeInTheDocument();
    expect(screen.getByLabelText("k")).toHaveValue(5);
    expect(screen.getByRole("button", { name: "Run evaluation" })).toBeInTheDocument();
    expect(requestedUrls()).toEqual([
      `/api/documents/${paper.id}/evals`,
      `/api/documents/${paper.id}/golden`,
    ]);
  });

  it("posts the chosen k, then shows the new run and its metrics without a manual refresh", async () => {
    selectDocument(paper);
    let history: EvalRunSummary[] = [];
    const created = runSummary({
      id: 3,
      k: 7,
      created_at: "2026-05-03T09:00:00Z",
      config: { ...baseConfig, k: 7 },
    });
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === `/api/documents/${paper.id}/evals` && init?.method === "POST") {
        history = [created];
        return jsonResponse(created);
      }
      if (url === `/api/documents/${paper.id}/evals`) {
        return jsonResponse(history);
      }
      if (url === `/api/documents/${paper.id}/golden`) {
        return jsonResponse(goldenSet);
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const user = userEvent.setup();
    renderDashboard();

    await screen.findByText(/no evaluation runs yet/i);
    await user.clear(screen.getByLabelText("k"));
    await user.type(screen.getByLabelText("k"), "7");
    await user.click(screen.getByRole("button", { name: "Run evaluation" }));

    const latest = await screen.findByRole("region", { name: "Latest run" });
    expect(within(latest).getByText("Retrieval hit rate @ k=7")).toBeInTheDocument();
    expect(within(latest).getByText("0.6667 (66.67%)")).toBeInTheDocument();
    expect(within(latest).getByText("Answer faithfulness")).toBeInTheDocument();
    expect(within(latest).getByText("0.5000 (50.00%)")).toBeInTheDocument();
    expect(within(latest).getByText("2026-05-03 09:00:00")).toBeInTheDocument();

    const postCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        String(input) === `/api/documents/${paper.id}/evals` && init?.method === "POST",
    );
    expect(postCall).toBeDefined();
    expect(JSON.parse(String(postCall?.[1]?.body))).toEqual({ k: 7 });
  });

  it("lists every run newest first with timestamps, k, metrics and comparability", async () => {
    selectDocument(paper);
    const latest = runSummary({
      id: 2,
      created_at: "2026-05-02T10:00:00Z",
      k: 10,
      config: { ...baseConfig, k: 10 },
    });
    const older = runSummary({
      id: 1,
      created_at: "2026-05-01T10:00:00Z",
      k: 5,
      comparable: false,
      flagged: true,
    });
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === `/api/documents/${paper.id}/evals`) {
        // Deliberately unsorted: the dashboard must order newest first itself.
        return jsonResponse([older, latest]);
      }
      if (url === `/api/documents/${paper.id}/golden`) {
        return jsonResponse(goldenSet);
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    renderDashboard();

    const history = await screen.findByRole("region", { name: "Run history" });
    const rows = within(history).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("Run #2")).toBeInTheDocument();
    expect(within(rows[0]).getByText("k = 10")).toBeInTheDocument();
    expect(within(rows[0]).getByText("2026-05-02 10:00:00")).toHaveAttribute(
      "datetime",
      "2026-05-02T10:00:00Z",
    );
    expect(within(rows[0]).getByText("0.6667 (66.67%)")).toBeInTheDocument();
    expect(within(rows[0]).getByText("0.5000 (50.00%)")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Run #1")).toBeInTheDocument();
    expect(within(rows[1]).getByText("2026-05-01 10:00:00")).toBeInTheDocument();
  });

  it("distinguishes a not-comparable run with text and names the differing config field", async () => {
    selectDocument(paper);
    const latest = runSummary({
      id: 2,
      k: 10,
      config: { ...baseConfig, k: 10 },
    });
    const older = runSummary({
      id: 1,
      k: 5,
      comparable: false,
      flagged: true,
    });
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === `/api/documents/${paper.id}/evals`) {
        return jsonResponse([latest, older]);
      }
      if (url === `/api/documents/${paper.id}/golden`) {
        return jsonResponse(goldenSet);
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    renderDashboard();

    const history = await screen.findByRole("region", { name: "Run history" });
    const rows = within(history).getAllByRole("listitem");
    expect(within(rows[0]).getByText("Comparable")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Not comparable")).toBeInTheDocument();
    expect(within(rows[1]).getByText("k differs (this run: 5; latest: 10).")).toBeInTheDocument();
  });

  it("expands a run with the keyboard to show every per-entry result", async () => {
    selectDocument(paper);
    const run = runSummary({ id: 2 });
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === `/api/documents/${paper.id}/evals`) {
        return jsonResponse([run]);
      }
      if (url === `/api/documents/${paper.id}/golden`) {
        return jsonResponse(goldenSet);
      }
      if (url === `/api/evals/${run.id}`) {
        return jsonResponse(runDetail(run));
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const user = userEvent.setup();
    renderDashboard();

    const toggle = await screen.findByRole("button", {
      name: `Show per-entry results for run ${run.id}`,
    });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    toggle.focus();
    await user.keyboard("{Enter}");

    await waitFor(() => expect(toggle).toHaveAttribute("aria-expanded", "true"));
    expect(requestedUrls()).toContain(`/api/evals/${run.id}`);

    const first = (await screen.findByRole("heading", { name: "Golden index 0" })).closest("li");
    const second = screen.getByRole("heading", { name: "Golden index 1" }).closest("li");
    expect(first).not.toBeNull();
    expect(second).not.toBeNull();
    expect(within(first as HTMLElement).getByText("Hit")).toBeInTheDocument();
    expect(
      within(first as HTMLElement).getByText(/Claims: 2; supported claims: 1/),
    ).toBeInTheDocument();
    expect(within(first as HTMLElement).getByText(/0\.5000 \(50\.00%\)/)).toBeInTheDocument();
    expect(
      within(first as HTMLElement).getByText(
        "Late filings incur a flat 200 credit penalty per return.",
      ),
    ).toBeInTheDocument();
    expect(within(second as HTMLElement).getByText("Miss")).toBeInTheDocument();
    expect(
      within(second as HTMLElement).getByText(/Claims: 1; supported claims: 0/),
    ).toBeInTheDocument();
  });

  it("surfaces a 422 golden-set error with guidance instead of crashing", async () => {
    selectDocument(paper);
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === `/api/documents/${paper.id}/evals`) {
        return jsonResponse([]);
      }
      if (url === `/api/documents/${paper.id}/golden`) {
        return jsonResponse({ detail: "The golden set is empty; add at least one entry." }, 422);
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    renderDashboard();

    expect(
      await screen.findByText(/the golden set is empty; add at least one entry\./i),
    ).toBeInTheDocument();
    expect(screen.getByText(/add at least one valid entry/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Eval dashboard" })).toBeInTheDocument();
  });

  it("shows the API 422 message and guidance when a run is rejected for a missing golden set", async () => {
    selectDocument(paper);
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === `/api/documents/${paper.id}/evals` && init?.method === "POST") {
        return jsonResponse({ detail: "The golden set is empty; add at least one entry." }, 422);
      }
      if (url === `/api/documents/${paper.id}/evals`) {
        return jsonResponse([]);
      }
      if (url === `/api/documents/${paper.id}/golden`) {
        return jsonResponse({ detail: "The golden set is empty; add at least one entry." }, 422);
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const user = userEvent.setup();
    renderDashboard();

    await screen.findByText(/no evaluation runs yet/i);
    await user.click(screen.getByRole("button", { name: "Run evaluation" }));

    const alert = await screen.findByText(/could not start the evaluation/i);
    expect(alert).toHaveTextContent("The golden set is empty; add at least one entry.");
    expect(alert).toHaveTextContent(/add at least one valid entry/i);
  });
});
