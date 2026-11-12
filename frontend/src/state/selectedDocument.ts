/**
 * The one document the user has chosen to question (Locked intent #3).
 *
 * Selection is app state, not route state: the Library writes it and the Chat
 * page reads it, so it must survive navigation between the two. A small
 * module-level store with `useSyncExternalStore` keeps both pages on the same
 * value without introducing a provider or a new dependency, and mirroring it
 * into `sessionStorage` keeps the target across a page reload in the same tab
 * (one user, one machine — there is nothing to share between tabs).
 */

import { useSyncExternalStore } from "react";

import type { Document } from "../types";

const STORAGE_KEY = "khaleev.selected-document";

type Listener = () => void;

const listeners = new Set<Listener>();

let current: Document | null = readStored();

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
  if (current === null) {
    return;
  }
  current = null;
  persist(null);
  notify();
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
