/**
 * The cold-load ghost (T32, Locked intent #17's stale-selection rule).
 *
 * A persisted selection can outlive its document, and a reload straight onto
 * `/chat` has no recorded document list in module state — only the ids the
 * previous visit persisted beside the selection. `Chat` re-checks the selection
 * against those ids in a layout effect, which React commits **before** the
 * browser paints, so the "Questioning {title}" strip is never shown for a frame
 * and the plain empty state is what a cold load displays.
 *
 * The honest limit of this file: jsdom does not paint, and React Testing
 * Library flushes effects inside `act`, so the paint timing itself is not
 * observable here — nor would a plain effect fail these assertions. The
 * guarantee is structural (`useLayoutEffect` in the page); this file is the
 * mount-level regression test that a cold load discards the ghost selection with
 * no request, no error and no trace of the title in the markup.
 */

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Document } from "../../types";

const STORAGE_KEY = "khaleev.selected-document";
const KNOWN_IDS_KEY = "khaleev.known-documents";

/** The live document the persisted id list knows about. */
const other: Document = {
  id: 2,
  title: "Other.pdf",
  page_count: 1,
  created_at: "2026-03-04T08:00:00Z",
};

/** The persisted selection no document list contains any more. */
const ghost: Document = {
  id: 999,
  title: "Ghost Report.pdf",
  page_count: 4,
  created_at: "2026-01-01T00:00:00",
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Chat on a cold load", () => {
  it("drops a persisted selection the persisted id list excludes, before it can be seen", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);

    // Exactly what the previous visit left behind: a selection, and an id list
    // that does not contain it.
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(ghost));
    sessionStorage.setItem(KNOWN_IDS_KEY, JSON.stringify([other.id]));

    // Mimic the reload: the store and the page are imported fresh, so the store
    // reads `sessionStorage` and the page binds to that same fresh module.
    vi.resetModules();
    const store = await import("../../state/selectedDocument");
    const { Chat } = await import("../Chat");

    const { container } = render(
      <MemoryRouter>
        <Chat />
      </MemoryRouter>,
    );

    // The plain empty state is rendered, from a store that no longer holds the
    // ghost: the page's own reconcile call cleared this very module instance.
    expect(store.getSelectedDocument()).toBeNull();
    expect(screen.getByRole("heading", { name: "Chat" })).toBeInTheDocument();
    expect(screen.getByText(/no document selected yet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /go to the library/i })).toHaveAttribute("href", "/");

    // The selected-document strip and the question form are not.
    expect(screen.queryByRole("region", { name: "Selected document" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Question")).not.toBeInTheDocument();

    // Nor is the ghost's title, in any case form, anywhere in the markup.
    expect(screen.queryByText(/questioning/i)).not.toBeInTheDocument();
    const markup = container.innerHTML.toLowerCase();
    expect(markup).not.toContain("ghost report");
    expect(markup).not.toContain("ghost report.pdf");

    // The discard is silent: no error and no notice.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(/does not exist/i)).not.toBeInTheDocument();

    // And it mints no request: the page only reads module state.
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
