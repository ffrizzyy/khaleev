/**
 * The minimal landing contract (T25, locked intent 17).
 *
 * The Library is upload + documents, nothing else: a simplified hero, the
 * retained selection banner, the document list and — only when at least one
 * document exists — a client-side search field in the "Your documents" header.
 *
 * Structure, roles and text only — never a class name. The landing page issues
 * exactly one request (`GET /api/documents`); typing in the search narrows the
 * already-loaded list and must not add one.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getSelectedDocument, selectDocument } from "../../state/selectedDocument";
import type { Document } from "../../types";
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

const other: Document = {
  id: 2,
  title: "Other.pdf",
  page_count: 1,
  created_at: "2026-03-04T08:00:00Z",
};

/** The document list is the only endpoint the landing page is allowed to read. */
function installApi(documents: readonly Document[]) {
  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url === "/api/documents" && method === "GET") {
      return jsonResponse(documents);
    }
    throw new Error(`Unexpected request: ${method} ${url}`);
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Library minimal landing", () => {
  it("shows the simplified hero: headline, one supporting line and the Upload PDF control", async () => {
    installApi([]);
    render(<Library />);

    await screen.findByText(/no documents yet/i);

    // `page-cited answers` stays one unbroken text node, and the headline no
    // longer carries "and evaluation metrics".
    const headline = screen.getByText(/page-cited answers/i);
    expect(headline.textContent).toMatch(/page-cited answers/i);
    expect(headline.textContent).not.toMatch(/evaluation metrics/i);

    expect(
      screen.getByText("Upload a PDF, then pick the one document you want to question."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText<HTMLInputElement>("Upload PDF")).toBeInTheDocument();
  });

  it("carries no eyebrow, no helper sentence and no illustration", async () => {
    installApi([]);
    const { container } = render(<Library />);

    await screen.findByText(/no documents yet/i);

    // The old "Upload a PDF" eyebrow and the helper sentence under the button.
    expect(screen.queryByText("Upload a PDF", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText(/pick a pdf from your machine/i)).not.toBeInTheDocument();

    // With an empty library the only thing that could draw an SVG is the
    // removed hero illustration, so the page must contain none at all.
    expect(container.querySelectorAll("svg")).toHaveLength(0);
  });

  it("carries neither the Selected document row nor the Latest eval run card", async () => {
    installApi([paper]);
    render(<Library />);

    await screen.findByText("Paper.pdf");

    expect(screen.queryByText("Selected document")).not.toBeInTheDocument();
    expect(screen.queryByText("Latest eval run")).not.toBeInTheDocument();
    expect(screen.queryByText(/golden set/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/document detail/i)).not.toBeInTheDocument();
  });

  it("issues exactly one request: the document list", async () => {
    // A second endpoint would reject here, so only GET /api/documents answers.
    installApi([paper]);
    render(<Library />);

    await screen.findByText("Paper.pdf");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/documents");
  });

  it("renders no search field when the library is empty", async () => {
    installApi([]);
    render(<Library />);

    await screen.findByText(/no documents yet/i);
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
  });

  it("renders no selection banner when the library is empty", async () => {
    installApi([]);
    render(<Library />);

    // There is nothing to select, so the sentence would be noise: the page is
    // hero, then the "Your documents" heading and its empty-state sentence.
    await screen.findByText(/no documents yet/i);
    expect(screen.queryByText(/no document selected for Q&A yet/i)).not.toBeInTheDocument();
  });

  it("renders a labelled search field once at least one document exists", async () => {
    installApi([paper]);
    render(<Library />);

    await screen.findByText("Paper.pdf");
    expect(screen.getByRole("searchbox", { name: "Search documents" })).toBeInTheDocument();
  });

  it("filters the list by title, case-insensitively, without issuing a request", async () => {
    const user = userEvent.setup();
    installApi([paper, other]);
    render(<Library />);

    await screen.findByText("Paper.pdf");
    const search = screen.getByRole("searchbox", { name: "Search documents" });
    const requestsBeforeTyping = fetchMock.mock.calls.length;

    await user.type(search, "PAPER");

    expect(screen.getByText("Paper.pdf")).toBeInTheDocument();
    expect(screen.queryByText("Other.pdf")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.length).toBe(requestsBeforeTyping);

    await user.clear(search);

    expect(await screen.findByText("Other.pdf")).toBeInTheDocument();
    expect(screen.getByText("Paper.pdf")).toBeInTheDocument();
    expect(fetchMock.mock.calls.length).toBe(requestsBeforeTyping);
  });

  it("keeps the field while the filter matches nothing, because the count is taken before filtering", async () => {
    const user = userEvent.setup();
    installApi([paper, other]);
    render(<Library />);

    await screen.findByText("Paper.pdf");
    const search = screen.getByRole("searchbox", { name: "Search documents" });

    await user.type(search, "no such title");

    expect(screen.getByText("No documents match your search.")).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search documents" })).toBeInTheDocument();
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });

  it("restores the persisted query when the page remounts", async () => {
    const user = userEvent.setup();
    installApi([paper, other]);
    const first = render(<Library />);

    await screen.findByText("Paper.pdf");
    await user.type(screen.getByRole("searchbox", { name: "Search documents" }), "paper");

    expect(sessionStorage.getItem("khaleev.search-query")).toBe(JSON.stringify("paper"));

    first.unmount();
    render(<Library />);

    // The list must load before the field can exist: it is only rendered when
    // the library holds at least one document.
    expect(await screen.findByRole("searchbox", { name: "Search documents" })).toHaveValue("paper");
    expect(screen.getByText("Paper.pdf")).toBeInTheDocument();
    expect(screen.queryByText("Other.pdf")).not.toBeInTheDocument();
  });

  it("keeps the selection banner for the Q&A target", async () => {
    installApi([paper]);
    selectDocument(paper);
    render(<Library />);

    await screen.findByText("Paper.pdf");
    expect(screen.getByText(/Q&A target: Paper\.pdf/)).toBeInTheDocument();
  });

  it("keeps the selection banner empty state when nothing is selected", async () => {
    installApi([paper]);
    render(<Library />);

    await screen.findByText("Paper.pdf");
    expect(screen.getByText(/no document selected for Q&A yet/i)).toBeInTheDocument();
  });

  it("silently discards a persisted selection that is no longer in the list", async () => {
    installApi([other]);
    selectDocument(paper);
    render(<Library />);

    // The list is authoritative: the vanished id is gone before the banner can
    // name it, and the page explains nothing — a deleted document is not an error.
    expect(await screen.findByText("Other.pdf")).toBeInTheDocument();
    expect(getSelectedDocument()).toBeNull();
    expect(screen.getByText(/no document selected for Q&A yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/does not exist/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Q&A target:/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("leaves a live selection alone when its document is in the list", async () => {
    installApi([paper, other]);
    selectDocument(paper);
    render(<Library />);

    await screen.findByText("Paper.pdf");
    expect(getSelectedDocument()?.id).toBe(paper.id);
    expect(screen.getByText(/Q&A target: Paper\.pdf/)).toBeInTheDocument();
  });

  it("still reports a genuine failure to load the library", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Database unavailable" }, 500));
    render(<Library />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not load the library: Database unavailable");
  });
});
