/**
 * The top-bar search query (T23).
 *
 * SPEC's API surface has no search endpoint, so the search is a purely local
 * filter over the document list the Library already holds. The value lives in
 * app state so the field mounted in the shell survives navigation: type on
 * Chat, come back to the Library, and the same query still applies.
 *
 * The store mirrors `selectedDocument.ts`: a module-level value plus
 * `useSyncExternalStore`, with no provider and no new dependency.
 */

import { useSyncExternalStore } from "react";

type Listener = () => void;

const listeners = new Set<Listener>();

let currentQuery = "";

function notify(): void {
  for (const listener of listeners) {
    listener();
  }
}

/** The current query; an empty string means "show everything". */
export function getSearchQuery(): string {
  return currentQuery;
}

/** Replace the query (the search field's `onChange`). */
export function setSearchQuery(query: string): void {
  if (query === currentQuery) {
    return;
  }
  currentQuery = query;
  notify();
}

/** Forget the query, e.g. after a test or a reset. */
export function clearSearchQuery(): void {
  setSearchQuery("");
}

/** Subscribe to query changes; returns the unsubscribe function. */
export function subscribeSearchQuery(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** React binding: re-renders the caller when the query changes. */
export function useSearchQuery(): string {
  return useSyncExternalStore(subscribeSearchQuery, getSearchQuery, getSearchQuery);
}
