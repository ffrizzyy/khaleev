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
 * the last document list the app loaded and reconciles the selection against it.
 * Both helpers are request-free; the Library records the list it already
 * fetched, and the Chat and Eval dashboard pages re-check the selection on
 * mount (Locked intent #17, the stale-selection rule).
 *
 * That list's ids are mirrored into `sessionStorage` beside the selection,
 * because module state resets on a reload: without the ids, a cold load
 * straight onto `/chat` has no list to reconcile against and would confidently
 * name a document that is gone. Persisting them is safe — an id list is not a
 * selection, and a stale id is still caught by the Library's next
 * `GET /api/documents` (which overwrites the list) and by the ask endpoint's
 * 404. Strictly better than showing a ghost.
 */

import { useSyncExternalStore } from "react";

import type { Document } from "../types";

const STORAGE_KEY = "khaleev.selected-document";
const KNOWN_IDS_KEY = "khaleev.known-documents";

type Listener = () => void;

const listeners = new Set<Listener>();

let current: Document | null = readStored();

/**
 * The document list the app last loaded from `GET /api/documents`, or `null`
 * when no page has loaded it yet. A page that has not seen a list must never
 * guess: `reconcileSelection` is a no-op until something records one.
 */
let knownDocuments: readonly Document[] | null = null;

/**
 * True only for a positive integer. `1.5`, `-1`, `0` and `Infinity` are all
 * `number`s but none of them is an id or a page count: a persisted value that
 * carries one is corrupt — hand-edited storage, or `JSON.parse` silently
 * overflowing `1e999` to `Infinity` — and must not be trusted.
 */
function isPositiveInteger(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function isDocument(value: unknown): value is Document {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  // Ids and page counts are positive integers in the API contract this type
  // mirrors (`DocumentOut.page_count` is `Field(ge=1)`), so a persisted
  // selection that fails either check is not a document: it degrades to "no
  // selection" rather than naming a document the user cannot have chosen.
  return (
    isPositiveInteger(record.id) &&
    typeof record.title === "string" &&
    isPositiveInteger(record.page_count) &&
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

/**
 * The ids of the last document list the app loaded, as persisted on the
 * previous visit, or `null` when none was recorded or the value is unusable.
 * Ids only — never the documents themselves. An entry that is not a positive
 * integer makes the whole value unusable, exactly as corrupt JSON does.
 */
function readKnownIds(): number[] | null {
  try {
    const raw = sessionStorage.getItem(KNOWN_IDS_KEY);
    if (raw === null) {
      return null;
    }
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed) || !parsed.every(isPositiveInteger)) {
      return null;
    }
    return parsed as number[];
  } catch {
    // Corrupt JSON or unavailable storage means "no list": the reconciliation
    // then stays a no-op rather than guessing at a list it cannot trust.
    return null;
  }
}

function persistKnownIds(ids: readonly number[] | null): void {
  try {
    if (ids === null) {
      sessionStorage.removeItem(KNOWN_IDS_KEY);
    } else {
      sessionStorage.setItem(KNOWN_IDS_KEY, JSON.stringify(ids));
    }
  } catch {
    // Module state still reconciles this visit; only the next cold load loses
    // its fallback, which degrades to the no-op it was before T28.
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
  // The recorded lists — module state and the persisted ids — belong to the same
  // lifetime as the selection: the shared test setup calls this before every
  // test, which must also forget them so one test cannot leak a document list
  // into the next. Dropping the persisted ids also means a cleared selection
  // cannot be resurrected by a cold load.
  knownDocuments = null;
  persistKnownIds(null);
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
  // Persist the ids before reconciling, so a selection cleared here takes the
  // id list with it: nothing stale survives into the next cold load.
  persistKnownIds(documents.map((document) => document.id));
  reconcileSelection();
}

/**
 * Re-check the current selection against the recorded list and clear it when
 * the id is absent.
 *
 * Returns `true` only when it actually cleared something. It is a no-op — and
 * returns `false` — when no list has been recorded, so the Chat page and the
 * Eval dashboard can call it on mount without loading the list themselves and
 * without inventing a request their tests pin against. A cold load has no
 * module-level list, so the ids persisted by the last `rememberDocuments` stand
 * in; only a persisted list that exists and excludes the id clears it.
 */
export function reconcileSelection(): boolean {
  const selected = current;
  if (selected === null) {
    return false;
  }
  const knownIds: readonly number[] | null =
    knownDocuments === null ? readKnownIds() : knownDocuments.map((document) => document.id);
  if (knownIds === null) {
    return false;
  }
  if (knownIds.includes(selected.id)) {
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
