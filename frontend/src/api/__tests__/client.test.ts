import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, API_BASE_URL, apiRequest, isApiError } from "../client";
import {
  askDocument,
  deleteDocument,
  getDocument,
  getPageText,
  listDocuments,
  uploadDocument,
} from "../documents";
import { getEvalRun, getGoldenSet, listEvalRuns, startEval } from "../evals";
import { getConfig, updateConfig } from "../config";

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function lastRequest(): { url: string; init: RequestInit } {
  const [url, init] = fetchMock.mock.calls[0] ?? [];
  if (typeof url !== "string" || init === undefined) {
    throw new Error("fetch was not called with a URL and an init object");
  }
  return { url, init };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiRequest", () => {
  it("prefixes every path with the /api base URL", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));

    await apiRequest("/documents");

    expect(API_BASE_URL).toBe("/api");
    expect(lastRequest().url).toBe("/api/documents");
  });

  it("encodes a JSON body and declares the content type", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ answer: "A", citations: [] }));

    await apiRequest("/documents/1/ask", { method: "POST", json: { question: "Why?" } });

    const { init } = lastRequest();
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ question: "Why?" }));
  });

  it("returns the parsed JSON body of a successful response", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: 4,
        title: "Paper.pdf",
        page_count: 3,
        created_at: "2026-01-01T00:00:00Z",
      }),
    );

    const document = await apiRequest<{ id: number; title: string }>("/documents/4");

    expect(document.id).toBe(4);
    expect(document.title).toBe("Paper.pdf");
  });

  it("throws a typed ApiError carrying the status and the JSON detail", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "Document 7 does not exist" }, 404));

    const reason: unknown = await apiRequest("/documents/7").catch((error: unknown) => error);

    expect(isApiError(reason)).toBe(true);
    if (!isApiError(reason)) {
      throw new Error("expected the rejected value to be an ApiError");
    }
    expect(reason).toBeInstanceOf(ApiError);
    expect(reason.status).toBe(404);
    expect(reason.detail).toBe("Document 7 does not exist");
    expect(reason.message).toBe("Document 7 does not exist");
  });

  it("surfaces a 400 with the API's own detail message", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "The upload is not a PDF" }, 400));

    const reason: unknown = await apiRequest("/documents", { method: "POST" }).catch(
      (error: unknown) => error,
    );

    if (!isApiError(reason)) {
      throw new Error("expected the rejected value to be an ApiError");
    }
    expect(reason.status).toBe(400);
    expect(reason.detail).toBe("The upload is not a PDF");
  });

  it("flattens FastAPI 422 validation details into one readable message", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          detail: [
            {
              loc: ["body", "question"],
              msg: "String should have at least 1 character",
              type: "string_too_short",
            },
          ],
        },
        422,
      ),
    );

    const reason: unknown = await apiRequest("/documents/1/ask", {
      method: "POST",
      json: { question: "" },
    }).catch((error: unknown) => error);

    if (!isApiError(reason)) {
      throw new Error("expected the rejected value to be an ApiError");
    }
    expect(reason.status).toBe(422);
    expect(reason.detail).toContain("String should have at least 1 character");
  });

  it("falls back to a status message when the error body is not JSON", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response("Upstream generator unavailable", { status: 503 }),
    );

    const reason: unknown = await apiRequest("/documents/1/ask", {
      method: "POST",
      json: { question: "Why?" },
    }).catch((error: unknown) => error);

    if (!isApiError(reason)) {
      throw new Error("expected the rejected value to be an ApiError");
    }
    expect(reason.status).toBe(503);
    expect(reason.detail).toContain("503");
  });
});

describe("documents API", () => {
  it("lists documents with a GET request", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));

    await listDocuments();

    const { url, init } = lastRequest();
    expect(url).toBe("/api/documents");
    expect(init.method ?? "GET").toBe("GET");
  });

  it("fetches a document detail with a GET request", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        id: 2,
        title: "A.pdf",
        page_count: 1,
        created_at: "2026-01-01T00:00:00Z",
        content_hash: "abc",
      }),
    );

    await getDocument(2);

    expect(lastRequest().url).toBe("/api/documents/2");
  });

  it("fetches one page's extracted text", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ document_id: 2, page_number: 3, text: "Page three" }),
    );

    await getPageText(2, 3);

    expect(lastRequest().url).toBe("/api/documents/2/pages/3");
  });

  it("deletes a document with a DELETE request", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 2, deleted: true }));

    await deleteDocument(2);

    const { url, init } = lastRequest();
    expect(url).toBe("/api/documents/2");
    expect(init.method).toBe("DELETE");
  });

  it("uploads a PDF as multipart without setting Content-Type manually", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { id: 9, title: "new.pdf", page_count: 2, created_at: "2026-01-01T00:00:00Z" },
        201,
      ),
    );
    const file = new File(["%PDF-1.4"], "new.pdf", { type: "application/pdf" });

    await uploadDocument(file);

    const { url, init } = lastRequest();
    expect(url).toBe("/api/documents");
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
    const body = init.body as FormData;
    expect(body.get("file")).toBe(file);
  });

  it("asks a question about one document with a JSON body", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        answer: "Because of page 4.",
        citations: [{ page: 4, quote: "flat 200 credit" }],
      }),
    );

    const answer = await askDocument(2, "What penalty applies?");

    const { url, init } = lastRequest();
    expect(url).toBe("/api/documents/2/ask");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ question: "What penalty applies?" }));
    expect(answer.citations[0]?.page).toBe(4);
  });
});

describe("evals API", () => {
  it("reads the golden set for a document", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ document_id: 3, revision: "r1", entries: [] }));

    await getGoldenSet(3);

    expect(lastRequest().url).toBe("/api/documents/3/golden");
  });

  it("starts an eval run with the default k when none is given", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 11, document_id: 3, k: 5 }));

    await startEval(3);

    const { url, init } = lastRequest();
    expect(url).toBe("/api/documents/3/evals");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({}));
  });

  it("passes an explicit k to the eval run", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 12, document_id: 3, k: 10 }));

    await startEval(3, 10);

    expect(lastRequest().init.body).toBe(JSON.stringify({ k: 10 }));
  });

  it("reads one eval run with its per-entry results", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 11, entries: [] }));

    await getEvalRun(11);

    expect(lastRequest().url).toBe("/api/evals/11");
  });

  it("lists a document's eval history", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));

    await listEvalRuns(3);

    expect(lastRequest().url).toBe("/api/documents/3/evals");
  });
});

describe("config API", () => {
  it("reads the current config", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        k: 5,
        embedder: "all-MiniLM-L6-v2",
        generator: "ollama",
        ollama_base_url: "http://localhost:11434",
        ollama_model: "llama3.1:8b",
      }),
    );

    const config = await getConfig();

    expect(lastRequest().url).toBe("/api/config");
    expect(config.k).toBe(5);
  });

  it("sends a partial config update with PUT", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        k: 10,
        embedder: "all-MiniLM-L6-v2",
        generator: "ollama",
        ollama_base_url: "http://localhost:11434",
        ollama_model: "llama3.1:8b",
      }),
    );

    await updateConfig({ k: 10 });

    const { url, init } = lastRequest();
    expect(url).toBe("/api/config");
    expect(init.method).toBe("PUT");
    expect(init.body).toBe(JSON.stringify({ k: 10 }));
  });
});
