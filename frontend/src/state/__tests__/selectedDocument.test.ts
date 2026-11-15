/**
 * The selected-document store and its stale-id reconciliation (T26, T28).
 *
 * The persisted selection can outlive the document it names: a delete, or a
 * reset of the data directory, leaves an id in `sessionStorage` that no longer
 * exists. The store therefore carries the last document list the app loaded
 * (`rememberDocuments`) and can re-check the selection against it
 * (`reconcileSelection`) — both request-free, both silent. Nothing here touches
 * `fetch`.
 *
 * The list is not module state only: `rememberDocuments` persists its ids beside
 * the selection, so a cold load straight onto `/chat` — no page has fetched a
 * list in this tab yet — still has something to reconcile against. The
 * cold-start tests below seed `sessionStorage`, re-import the module with
 * `vi.resetModules()` and prove the three cases: an id the list excludes is
 * cleared, an id it includes survives, and a corrupt list clears nothing.
 */

import { describe, expect, it, vi } from "vitest";

import {
  clearSelectedDocument,
  getSelectedDocument,
  reconcileSelection,
  rememberDocuments,
  selectDocument,
} from "../selectedDocument";
import type { Document } from "../../types";

const STORAGE_KEY = "khaleev.selected-document";
const KNOWN_IDS_KEY = "khaleev.known-documents";

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

/** The document named by the persisted selection in the cold-load tests. */
const ghost: Document = {
  id: 999,
  title: "Ghost Report.pdf",
  page_count: 4,
  created_at: "2026-01-01T00:00:00",
};

/**
 * Mimic a page reload: drop the module registry so the next import re-evaluates
 * the store from `sessionStorage` alone, exactly like a cold load of `/chat`.
 */
async function importAfterColdStart(): Promise<typeof import("../selectedDocument")> {
  vi.resetModules();
  return import("../selectedDocument");
}

describe("selected document store", () => {
  it("keeps the existing public API: select, read and clear", () => {
    selectDocument(paper);

    expect(getSelectedDocument()).toEqual(paper);
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe(JSON.stringify(paper));

    clearSelectedDocument();

    expect(getSelectedDocument()).toBeNull();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});

describe("rememberDocuments", () => {
  it("clears a selection whose id is absent from the list", () => {
    selectDocument(paper);

    rememberDocuments([other]);

    expect(getSelectedDocument()).toBeNull();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("keeps a selection whose id is in the list", () => {
    selectDocument(paper);

    rememberDocuments([other, paper]);

    expect(getSelectedDocument()).toEqual(paper);
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe(JSON.stringify(paper));
  });

  it("clears a selection when the list is empty", () => {
    selectDocument(paper);

    rememberDocuments([]);

    expect(getSelectedDocument()).toBeNull();
  });

  it("is harmless when nothing is selected", () => {
    expect(() => rememberDocuments([paper])).not.toThrow();
    expect(getSelectedDocument()).toBeNull();
  });

  it("persists the ids beside the selection for the next cold load", () => {
    selectDocument(paper);

    rememberDocuments([other, paper]);

    expect(sessionStorage.getItem(KNOWN_IDS_KEY)).toBe(JSON.stringify([other.id, paper.id]));
  });
});

describe("clearSelectedDocument", () => {
  it("forgets the persisted id list as well as the selection", () => {
    selectDocument(paper);
    rememberDocuments([paper]);
    expect(sessionStorage.getItem(KNOWN_IDS_KEY)).toBe(JSON.stringify([paper.id]));

    clearSelectedDocument();

    expect(sessionStorage.getItem(KNOWN_IDS_KEY)).toBeNull();
  });
});

describe("reconcileSelection", () => {
  it("is a no-op when no list has been recorded, so a page never guesses", () => {
    selectDocument(paper);

    expect(reconcileSelection()).toBe(false);
    expect(getSelectedDocument()).toEqual(paper);
  });

  it("returns true only when it actually cleared a stale selection", () => {
    selectDocument(paper);
    rememberDocuments([other]);

    // `rememberDocuments` already cleared it, so a second check changes nothing.
    expect(reconcileSelection()).toBe(false);
    expect(getSelectedDocument()).toBeNull();
  });

  it("clears a selection recorded before the list arrives", () => {
    rememberDocuments([]);
    selectDocument(paper);

    expect(reconcileSelection()).toBe(true);
    expect(getSelectedDocument()).toBeNull();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("leaves a live selection alone", () => {
    rememberDocuments([paper]);
    selectDocument(paper);

    expect(reconcileSelection()).toBe(false);
    expect(getSelectedDocument()).toEqual(paper);
  });

  it("forgets the recorded list when the shared setup clears the selection", () => {
    selectDocument(paper);
    rememberDocuments([other]);
    clearSelectedDocument();
    selectDocument(paper);

    // A fresh test must not inherit the previous test's list.
    expect(reconcileSelection()).toBe(false);
    expect(getSelectedDocument()).toEqual(paper);
  });
});

describe("cold start straight onto /chat", () => {
  it("clears a persisted selection the persisted id list excludes", async () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(ghost));
    sessionStorage.setItem(KNOWN_IDS_KEY, JSON.stringify([paper.id]));

    const store = await importAfterColdStart();

    // No page fetched a list in this tab; the persisted ids are all there is.
    expect(store.getSelectedDocument()).toEqual(ghost);
    expect(store.reconcileSelection()).toBe(true);
    expect(store.getSelectedDocument()).toBeNull();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
    // A cleared selection takes the id list with it, so it cannot be revived.
    expect(sessionStorage.getItem(KNOWN_IDS_KEY)).toBeNull();
  });

  it("keeps a persisted selection the persisted id list includes", async () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(paper));
    sessionStorage.setItem(KNOWN_IDS_KEY, JSON.stringify([other.id, paper.id]));

    const store = await importAfterColdStart();

    expect(store.reconcileSelection()).toBe(false);
    expect(store.getSelectedDocument()).toEqual(paper);
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe(JSON.stringify(paper));
    expect(sessionStorage.getItem(KNOWN_IDS_KEY)).toBe(JSON.stringify([other.id, paper.id]));
  });

  it("treats corrupt persisted ids as no list and clears nothing", async () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(ghost));
    sessionStorage.setItem(KNOWN_IDS_KEY, "{not json");

    const store = await importAfterColdStart();

    expect(store.reconcileSelection()).toBe(false);
    expect(store.getSelectedDocument()).toEqual(ghost);
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe(JSON.stringify(ghost));
  });

  it("treats a list that is not numbers as no list and clears nothing", async () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(ghost));
    sessionStorage.setItem(KNOWN_IDS_KEY, JSON.stringify([String(ghost.id)]));

    const store = await importAfterColdStart();

    expect(store.reconcileSelection()).toBe(false);
    expect(store.getSelectedDocument()).toEqual(ghost);
  });
});
