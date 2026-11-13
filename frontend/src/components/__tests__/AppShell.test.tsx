import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../../App";
import { clearSelectedDocument } from "../../state/selectedDocument";
import { setSearchQuery } from "../../state/searchQuery";
import type { Document } from "../../types";

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

/** The library list is the only endpoint the shell + Library need here. */
function installLibraryApi(documents: readonly Document[]) {
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
  clearSelectedDocument();
  setSearchQuery("");
  sessionStorage.clear();
  window.history.pushState({}, "", "/");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AppShell", () => {
  it("renders the rail as the Primary navigation with the three destinations", async () => {
    installLibraryApi([paper]);
    render(<App />);

    const nav = screen.getByRole("navigation", { name: "Primary" });
    const library = within(nav).getByRole("link", { name: "Library" });
    expect(library).toHaveAttribute("href", "/");
    expect(library).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Chat" })).toHaveAttribute("href", "/chat");
    expect(within(nav).getByRole("link", { name: "Eval dashboard" })).toHaveAttribute(
      "href",
      "/evals",
    );

    // The top-bar icon links are real destinations but never reuse the rail names.
    expect(screen.getByRole("link", { name: "Go to Library" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Go to the Eval dashboard" })).toHaveAttribute(
      "href",
      "/evals",
    );

    // The product heading survives, visually hidden, so the page keeps one h1.
    // (Asserted by role, never by class name: tests stay semantic.)
    expect(screen.getByRole("heading", { level: 1, name: "Khaleev" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("labels the top-bar search field", async () => {
    installLibraryApi([paper]);
    render(<App />);

    expect(screen.getByRole("searchbox", { name: "Search documents" })).toBeInTheDocument();
  });

  it("narrows the visible document list as the user types and restores it when cleared", async () => {
    const user = userEvent.setup();
    installLibraryApi([paper, other]);
    render(<App />);

    await screen.findByText("Paper.pdf");
    expect(screen.getByText("Other.pdf")).toBeInTheDocument();

    const search = screen.getByRole("searchbox", { name: "Search documents" });
    const requestsBeforeTyping = fetchMock.mock.calls.length;

    await user.type(search, "paper");

    expect(screen.getByText("Paper.pdf")).toBeInTheDocument();
    expect(screen.queryByText("Other.pdf")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.length).toBe(requestsBeforeTyping);

    await user.clear(search);

    expect(await screen.findByText("Other.pdf")).toBeInTheDocument();
    expect(screen.getByText("Paper.pdf")).toBeInTheDocument();
    expect(fetchMock.mock.calls.length).toBe(requestsBeforeTyping);
  });
});
