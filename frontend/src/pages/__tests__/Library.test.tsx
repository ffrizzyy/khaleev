import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSelectedDocument, getSelectedDocument } from "../../state/selectedDocument";
import type { Document } from "../../types";
import { Library } from "../Library";

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function pdfFile(name: string): File {
  return new File(["%PDF-1.4"], name, { type: "application/pdf" });
}

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

interface UploadPlan {
  document: Document;
  status?: number;
}

/**
 * A tiny in-memory stand-in for the document API. `fetch` is the only thing
 * mocked: the real `api/documents` module and its client run for real, so the
 * test exercises the actual multipart/JSON/error plumbing.
 */
function installApi(initial: readonly Document[], upload?: UploadPlan) {
  const documents = [...initial];
  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url === "/api/documents" && method === "GET") {
      return jsonResponse(documents);
    }
    if (url === "/api/documents" && method === "POST") {
      if (upload === undefined) {
        throw new Error("unexpected upload");
      }
      if (!documents.some((document) => document.id === upload.document.id)) {
        documents.push(upload.document);
      }
      return jsonResponse(upload.document, upload.status ?? 201);
    }
    const deleteMatch = /^\/api\/documents\/(\d+)$/.exec(url);
    if (deleteMatch !== null && method === "DELETE") {
      const id = Number(deleteMatch[1]);
      const index = documents.findIndex((document) => document.id === id);
      if (index >= 0) {
        documents.splice(index, 1);
      }
      return jsonResponse({ id, deleted: true });
    }
    throw new Error(`Unexpected request: ${method} ${url}`);
  });
  return documents;
}

function getRequestCount(): number {
  return fetchMock.mock.calls.filter(
    ([input, init]) => String(input) === "/api/documents" && (init?.method ?? "GET") === "GET",
  ).length;
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  clearSelectedDocument();
  sessionStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Library", () => {
  it("lists documents with title, page count and ingest date", async () => {
    installApi([paper]);
    render(<Library />);

    expect(screen.getByText(/loading documents/i)).toBeInTheDocument();

    expect(await screen.findByText("Paper.pdf")).toBeInTheDocument();
    expect(screen.getByText("3 pages")).toBeInTheDocument();
    expect(screen.getByText("2026-02-03")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders a readable message when the library cannot be loaded", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Database unavailable" }, 500));
    render(<Library />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Database unavailable");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows a freshly uploaded PDF without a manual reload", async () => {
    const user = userEvent.setup();
    installApi([], { document: paper });
    render(<Library />);

    await screen.findByText(/no documents yet/i);

    await user.upload(screen.getByLabelText<HTMLInputElement>("Upload PDF"), pdfFile("Paper.pdf"));

    expect(await screen.findByText("Paper.pdf")).toBeInTheDocument();
    expect(screen.queryByText(/no documents yet/i)).not.toBeInTheDocument();
    expect(getRequestCount()).toBe(2);
  });

  it("surfaces a duplicate upload and keeps a single row", async () => {
    const user = userEvent.setup();
    installApi([paper], { document: paper, status: 200 });
    render(<Library />);

    await screen.findByText("Paper.pdf");

    await user.upload(screen.getByLabelText<HTMLInputElement>("Upload PDF"), pdfFile("Paper.pdf"));

    expect(await screen.findByText(/already in your library/i)).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("removes a document only after the deletion is confirmed", async () => {
    const user = userEvent.setup();
    installApi([paper, other]);
    render(<Library />);

    await screen.findByText("Paper.pdf");

    await user.click(screen.getByRole("button", { name: "Delete Paper.pdf" }));

    expect(screen.getByText("Paper.pdf")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Confirm delete Paper.pdf" }));

    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(1));
    expect(screen.queryByText("Paper.pdf")).not.toBeInTheDocument();
    expect(screen.getByText("Other.pdf")).toBeInTheDocument();
  });

  it("marks a document as the Q&A target and persists the choice", async () => {
    const user = userEvent.setup();
    installApi([paper, other]);
    render(<Library />);

    await screen.findByText("Paper.pdf");

    await user.click(screen.getByRole("button", { name: "Select Paper.pdf" }));

    expect(screen.getByText(/Q&A target: Paper\.pdf/)).toBeInTheDocument();
    expect(getSelectedDocument()?.id).toBe(paper.id);
    expect(sessionStorage.getItem("khaleev.selected-document")).toContain(`"id":${paper.id}`);
  });

  it("clears the Q&A target when the selected document is deleted", async () => {
    const user = userEvent.setup();
    installApi([paper, other]);
    render(<Library />);

    await screen.findByText("Paper.pdf");
    await user.click(screen.getByRole("button", { name: "Select Paper.pdf" }));
    await user.click(screen.getByRole("button", { name: "Delete Paper.pdf" }));
    await user.click(screen.getByRole("button", { name: "Confirm delete Paper.pdf" }));

    await waitFor(() => expect(getSelectedDocument()).toBeNull());
    expect(screen.getByText(/no document selected for Q&A yet/i)).toBeInTheDocument();
  });
});
