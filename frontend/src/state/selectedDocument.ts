/**
 * The one document the user has chosen to question (Locked intent #3).
 *
 * Selection is app state, not route state: the Library writes it and the Chat
 * page reads it, so it must survive navigation between the two. A small
 * module-level store with `useSyncExternalStore` keeps both pages on the same
 * value without introducing a provider or a new dependency, and mirroring it
 * into `sessionStorage` keeps the target across a page reload in the same tab
 * (one user, one machine — there is nothing to share between tabs).
 *
 * A persisted id can outlive its document (a delete, or a reset data directory),
 * and the pages must never explain that as an error. The store therefore keeps
 * the last document list the app loaded — module state, not `sessionStorage`,
 * so it is never persisted or guessed at — and reconciles the selection against
 * it. Both helpers are request-free; the Library records the list it already
 * fetched, and the Chat and Eval dashboard pages re-check the selection on
 * mount (Locked intent #17, the stale-selection rule).
 */

import { useSyncExternalStore } from "react";

import type { Document } from "../types";

const STORAGE_KEY = "khaleev.selected-document";

type Listener = () => void;

const listeners = new Set<Listener>();

let current: Document | null = readStored();

/**
 * The document list the app last loaded from `GET /api/documents`, or `null`
 * when no page has loaded it yet. A page that has not seen a list must never
 * guess: `reconcileSelection` is a no-op until something records one.
 */
let knownDocuments: readonly Document[] | null = null;

function isDocument(value: unknown): value is Document {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  return (
    typeof record.id === "number" &&
    typeof record.title === "string" &&
    typeof record.page_count === "number" &&
    typeof record.created_at === "string"
  );
}

function readStored(): Document | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw === null) {
      return null;
    }
    const parsed: unknown = JSON.parse(raw);
    return isDocument(parsed) ? parsed : null;
  } catch {
    // Storage can be unavailable (privacy mode) or hold stale JSON; either way
    // an empty selection is the safe fallback and the app still works.
    return null;
  }
}

function persist(next: Document | null): void {
  try {
    if (next === null) {
      sessionStorage.removeItem(STORAGE_KEY);
    } else {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    }
  } catch {
    // The in-memory selection still drives this tab; only reload persistence
    // is lost.
  }
}

function notify(): void {
  for (const listener of listeners) {
    listener();
  }
}

/** The current Q&A target, or `null` when nothing is selected. */
export function getSelectedDocument(): Document | null {
  return current;
}

/** Make `document` the Q&A target for the Chat page. */
export function selectDocument(document: Document): void {
  current = document;
  persist(document);
  notify();
}

/** Forget the Q&A target, e.g. after its document is deleted. */
export function clearSelectedDocument(): void {
  // The recorded list belongs to the same lifetime as the selection: the shared
  // test setup calls this before every test, which must also forget the list so
  // one test cannot leak a document list into the next.
  knownDocuments = null;
  if (current === null) {
    return;
  }
  current = null;
  persist(null);
  notify();
}

/**
 * Record the document list the app just loaded, and discard a selection that is
 * no longer in it.
 *
 * This is the Library's call after `GET /api/documents`: the list is
 * authoritative, so an id that has vanished (its document was deleted, or the
 * data directory was reset) is cleared silently — no error text, no request, no
 * console output. The same call after a delete keeps the list authoritative.
 */
export function rememberDocuments(documents: readonly Document[]): void {
  knownDocuments = [...documents];
  reconcileSelection();
}

/**
 * Re-check the current selection against the recorded list and clear it when
 * the id is absent.
 *
 * Returns `true` only when it actually cleared something. It is a no-op — and
 * returns `false` — when no list has been recorded, so the Chat page and the
 * Eval dashboard can call it on mount without loading the list themselves and
 * without inventing a request their tests pin against.
 */
export function reconcileSelection(): boolean {
  const selected = current;
  if (selected === null || knownDocuments === null) {
    return false;
  }
  if (knownDocuments.some((document) => document.id === selected.id)) {
    return false;
  }
  clearSelectedDocument();
  return true;
}

/** Subscribe to selection changes; returns the unsubscribe function. */
export function subscribeSelectedDocument(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** React binding: re-renders the calling component when the target changes. */
export function useSelectedDocument(): Document | null {
  return useSyncExternalStore(subscribeSelectedDocument, getSelectedDocument, getSelectedDocument);
}
