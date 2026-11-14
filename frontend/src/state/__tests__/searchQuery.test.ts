import { describe, expect, it, vi } from "vitest";

import { getSearchQuery, setSearchQuery } from "../searchQuery";

const STORAGE_KEY = "khaleev.search-query";

describe("search query store", () => {
  it("mirrors the query into sessionStorage like the selected document", () => {
    setSearchQuery("paper");

    expect(getSearchQuery()).toBe("paper");
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe(JSON.stringify("paper"));
  });

  it("starts empty in the next test because the shared setup reset runs between tests", () => {
    expect(getSearchQuery()).toBe("");
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("restores a persisted query when the store module loads", async () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify("persisted"));

    vi.resetModules();
    const fresh = await import("../searchQuery");

    expect(fresh.getSearchQuery()).toBe("persisted");
  });

  it("falls back to an empty query when storage holds corrupt data", async () => {
    sessionStorage.setItem(STORAGE_KEY, "{not json");

    vi.resetModules();
    const fresh = await import("../searchQuery");

    expect(fresh.getSearchQuery()).toBe("");
  });
});
