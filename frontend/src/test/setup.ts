import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";

import { clearSearchQuery } from "../state/searchQuery";
import { clearSelectedDocument } from "../state/selectedDocument";

// Vitest runs without globals, so React Testing Library cannot register its own
// cleanup hook; do it explicitly so every test starts with an empty DOM.
afterEach(() => {
  cleanup();
});

// The app stores its cross-page state in module-level values mirrored into
// `sessionStorage`. Vitest reuses a worker (and therefore those modules) across
// test files, so reset both stores before every test or a value set in one test
// leaks into the next.
beforeEach(() => {
  clearSelectedDocument();
  clearSearchQuery();
  sessionStorage.clear();
});
