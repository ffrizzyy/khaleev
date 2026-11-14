/**
 * The selected-document store and its stale-id reconciliation (T26).
 *
 * The persisted selection can outlive the document it names: a delete, or a
 * reset of the data directory, leaves an id in `sessionStorage` that no longer
 * exists. The store therefore carries the last document list the app loaded
 * (`rememberDocuments`) and can re-check the selection against it
 * (`reconcileSelection`) — both request-free, both silent. Nothing here touches
 * `fetch`.
 */

import { describe, expect, it } from "vitest";

import {
  clearSelectedDocument,
  getSelectedDocument,
  reconcileSelection,
  rememberDocuments,
  selectDocument,
} from "../selectedDocument";
import type { Document } from "../../types";

const STORAGE_KEY = "khaleev.selected-document";

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
