import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Vitest runs without globals, so React Testing Library cannot register its own
// cleanup hook; do it explicitly so every test starts with an empty DOM.
afterEach(() => {
  cleanup();
});
