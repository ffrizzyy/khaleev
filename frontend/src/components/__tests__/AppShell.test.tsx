/**
 * The shell after T25: the inset panel, the Primary icon rail and the content
 * area. The top bar (pill search, the two circular icon links, the avatar) is
 * removed by locked intent 17, so these tests assert the rail's exact contract
 * and that nothing top-bar-shaped remains.
 *
 * Structure, roles and text only — never a class name. The search field lives
 * on the Library page now, so its behaviour is covered by
 * `pages/__tests__/Library.minimal.test.tsx`.
 */

import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../../App";
import { AppShell } from "../AppShell";
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

    // The product heading survives, visually hidden, so the page keeps one h1.
    // (Asserted by role, never by class name: tests stay semantic.)
    expect(screen.getByRole("heading", { level: 1, name: "Khaleev" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("renders no top bar: no banner, no searchbox and no duplicate icon links", () => {
    render(
      <MemoryRouter>
        <AppShell />
      </MemoryRouter>,
    );

    // A `<header>` outside a landmark would be a banner; the removed top bar was
    // one, so its absence is the contract.
    expect(screen.queryByRole("banner")).not.toBeInTheDocument();
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Go to Library" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Go to the Eval dashboard" }),
    ).not.toBeInTheDocument();

    // The rail keeps exactly its three real destinations.
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(nav).getAllByRole("link")).toHaveLength(3);
  });
});
