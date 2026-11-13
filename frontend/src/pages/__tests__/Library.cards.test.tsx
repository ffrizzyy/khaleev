import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSelectedDocument, selectDocument } from "../../state/selectedDocument";
import type { Document, DocumentDetail, EvalRunSummary, GoldenSet } from "../../types";
import { Library } from "../Library";

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const paper: Document = {
  id: 1,
  title: "Paper.pdf",
  page_count: 3,
  created_at: "2026-02-03T10:15:00Z",
};

const detail: DocumentDetail = {
  ...paper,
  content_hash: "abcdef1234567890ff",
};

const golden: GoldenSet = {
  document_id: 1,
  revision: "rev-abc",
  entries: [
    { question: "What is filed?", expected_answer: "A return.", expected_pages: [1] },
    { question: "What is the penalty?", expected_answer: "A flat fee.", expected_pages: [3] },
  ],
};

const latestRun: EvalRunSummary = {
  id: 2,
  document_id: 1,
  created_at: "2026-05-03T09:00:00Z",
  k: 5,
  embedder_id: "all-MiniLM-L6-v2",
  scorer_id: "nli-deberta-v3-small",
  hit_rate: 0.6667,
  faithfulness: 0.5,
  config: {},
  comparable: true,
  flagged: false,
};

const olderRun: EvalRunSummary = {
  ...latestRun,
  id: 1,
  created_at: "2026-05-02T09:00:00Z",
  k: 10,
  hit_rate: 1,
  faithfulness: 1,
  comparable: false,
  flagged: true,
};

interface ApiPlan {
  goldenResponse?: Response;
  runs?: readonly EvalRunSummary[];
}

/** Serve the list plus the three read-only endpoints the cards use. */
function installApi(plan: ApiPlan = {}) {
  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url === "/api/documents" && method === "GET") {
      return jsonResponse([paper]);
    }
    if (url === "/api/documents/1" && method === "GET") {
      return jsonResponse(detail);
    }
    if (url === "/api/documents/1/golden" && method === "GET") {
      return plan.goldenResponse ?? jsonResponse(golden);
    }
    if (url === "/api/documents/1/evals" && method === "GET") {
      return jsonResponse(plan.runs ?? []);
    }
    throw new Error(`Unexpected request: ${method} ${url}`);
  });
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

describe("Library cards", () => {
  it("shows the selected document's golden revision and entry count, and its detail", async () => {
    installApi();
    selectDocument(paper);
    render(<Library />);

    expect(await screen.findByText("Entries: 2")).toBeInTheDocument();
    expect(screen.getByText("Revision: rev-abc")).toBeInTheDocument();
    expect(screen.getByText("Pages: 3")).toBeInTheDocument();
    expect(screen.getByText("Ingested 2026-02-03")).toBeInTheDocument();
    expect(screen.getByText("Hash: abcdef123456")).toBeInTheDocument();

    // The two-across row is built from articles, never list items, so the
    // document list keeps exactly one list item.
    expect(screen.getAllByRole("article")).toHaveLength(2);
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("states the API's own message instead of zeros when the golden set is missing", async () => {
    installApi({
      goldenResponse: jsonResponse({ detail: "golden set file not found for this document" }, 404),
    });
    selectDocument(paper);
    render(<Library />);

    expect(
      await screen.findByText(/golden set file not found for this document/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Entries:/)).not.toBeInTheDocument();
  });

  it("shows an honest empty state with a link to the eval dashboard when there are no runs", async () => {
    installApi({ runs: [] });
    selectDocument(paper);
    render(<Library />);

    expect(await screen.findByText("No eval runs yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the Eval dashboard" })).toHaveAttribute(
      "href",
      "/evals",
    );
  });

  it("shows the latest run's two metrics and the two most recent run cards", async () => {
    installApi({ runs: [latestRun, olderRun] });
    selectDocument(paper);
    render(<Library />);

    expect(await screen.findByText("Latest eval run")).toBeInTheDocument();
    expect(screen.getByText("66.67%")).toBeInTheDocument();
    expect(screen.getByText("50.00%")).toBeInTheDocument();
    expect(screen.getByText("k = 5")).toBeInTheDocument();

    expect(screen.getByText("Run #2")).toBeInTheDocument();
    expect(screen.getByText("Run #1")).toBeInTheDocument();
    expect(screen.getAllByText("Comparable")).toHaveLength(1);
    expect(screen.getByText("Not comparable")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Open the Eval dashboard" })).toHaveLength(2);
  });
});
