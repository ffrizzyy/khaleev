/**
 * The top-bar search query (T23).
 *
 * SPEC's API surface has no search endpoint, so the search is a purely local
 * filter over the document list the Library already holds. The value lives in
 * app state so the field mounted in the shell survives navigation: type on
 * Chat, come back to the Library, and the same query still applies.
 *
 * The store mirrors `selectedDocument.ts`: a module-level value plus
 * `useSyncExternalStore`, no provider and no new dependency, and the value is
 * mirrored into `sessionStorage` so a reload in the same tab keeps the filter
 * the user was looking through (one user, one machine — there is nothing to
 * share between tabs).
 */

import { useSyncExternalStore } from "react";

const STORAGE_KEY = "khaleev.search-query";

type Listener = () => void;

const listeners = new Set<Listener>();

let currentQuery = readStored();

function readStored(): string {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw === null) {
      return "";
    }
    const parsed: unknown = JSON.parse(raw);
    return typeof parsed === "string" ? parsed : "";
  } catch {
    // Storage can be unavailable (privacy mode) or hold stale JSON; either way
    // an empty query is the safe fallback and the app still works.
    return "";
  }
}

function persist(next: string): void {
  try {
    if (next === "") {
      sessionStorage.removeItem(STORAGE_KEY);
    } else {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    }
  } catch {
    // The in-memory query still drives this tab; only reload persistence is
    // lost.
  }
}

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
  persist(query);
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
