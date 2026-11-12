import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSelectedDocument, selectDocument } from "../../state/selectedDocument";
import type { AnswerResponse, Citation, Document } from "../../types";
import { Chat } from "../Chat";

const fetchMock = vi.fn<typeof fetch>();

const paper: Document = {
  id: 1,
  title: "Paper.pdf",
  page_count: 8,
  created_at: "2026-02-03T10:15:00Z",
};

const citations: Citation[] = [
  { page: 4, quote: "flat 200 credit penalty per return" },
  { page: 7, quote: "filing window closes on 31 March" },
];

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((settle) => {
    resolve = settle;
  });
  return { promise, resolve };
}

function pageText(documentId: number, pageNumber: number): unknown {
  return {
    document_id: documentId,
    page_number: pageNumber,
    text: `Extracted text of page ${pageNumber}.`,
  };
}

function requestedUrls(): string[] {
  return fetchMock.mock.calls.map(([input]) => String(input));
}

function renderChat() {
  render(
    <MemoryRouter>
      <Chat />
    </MemoryRouter>,
  );
}

async function ask(question = "What penalty applies to late filings?"): Promise<void> {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Question"), question);
  await user.click(screen.getByRole("button", { name: "Ask" }));
}

/** Answer whose citations are the shared two, served from a canned ask route. */
function answerWith(citationList: readonly Citation[]): AnswerResponse {
  return {
    answer: "Late filings incur a flat 200 credit penalty per return.",
    citations: [...citationList],
  };
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

describe("Chat", () => {
  it("explains how to pick a document instead of asking when none is selected", () => {
    renderChat();

    expect(screen.getByRole("heading", { name: "Chat" })).toBeInTheDocument();
    expect(screen.getByText(/no document selected/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /library/i })).toHaveAttribute("href", "/");
    expect(screen.queryByLabelText("Question")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the selected document, asks about it, and opens the cited page in the viewer", async () => {
    selectDocument(paper);
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === `/api/documents/${paper.id}/ask`) {
        return jsonResponse(answerWith(citations));
      }
      const pageMatch = /^\/api\/documents\/(\d+)\/pages\/(\d+)$/.exec(url);
      if (pageMatch !== null) {
        return jsonResponse(pageText(Number(pageMatch[1]), Number(pageMatch[2])));
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const user = userEvent.setup();
    renderChat();

    expect(screen.getByText(/questioning Paper\.pdf/i)).toBeInTheDocument();
    expect(screen.getByText("8 pages")).toBeInTheDocument();

    await ask();

    expect(await screen.findByText(answerWith(citations).answer)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /page 4/i }));

    const viewer = await screen.findByRole("dialog", { name: "Page 4" });
    expect(viewer).toHaveFocus();
    expect(await screen.findByText("Extracted text of page 4.")).toBeInTheDocument();
    expect(requestedUrls()).toContain(`/api/documents/${paper.id}/pages/4`);
  });

  it("never shows text fetched for a page other than the one cited", async () => {
    selectDocument(paper);
    const pageFour = deferred<Response>();
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === `/api/documents/${paper.id}/ask`) {
        return jsonResponse(answerWith(citations));
      }
      if (url === `/api/documents/${paper.id}/pages/4`) {
        return pageFour.promise;
      }
      if (url === `/api/documents/${paper.id}/pages/7`) {
        return jsonResponse(pageText(paper.id, 7));
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const user = userEvent.setup();
    renderChat();

    await ask();
    await screen.findByText(answerWith(citations).answer);

    await user.click(screen.getByRole("button", { name: /page 4/i }));
    await user.click(screen.getByRole("button", { name: /page 7/i }));

    expect(await screen.findByText("Extracted text of page 7.")).toBeInTheDocument();

    await act(async () => {
      pageFour.resolve(jsonResponse(pageText(paper.id, 4)));
    });

    await waitFor(() =>
      expect(screen.queryByText("Extracted text of page 4.")).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("dialog", { name: "Page 7" })).toHaveTextContent(
      "Extracted text of page 7.",
    );
  });

  it("refuses a cited page outside the document's page range without fetching it", async () => {
    selectDocument(paper);
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === `/api/documents/${paper.id}/ask`) {
        return jsonResponse(answerWith([{ page: 9, quote: "Out of range." }]));
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const user = userEvent.setup();
    renderChat();

    await ask();
    await user.click(await screen.findByRole("button", { name: /page 9/i }));

    const viewer = await screen.findByRole("dialog", { name: "Page 9" });
    expect(viewer).toHaveTextContent(/outside/i);
    expect(requestedUrls()).not.toContain(`/api/documents/${paper.id}/pages/9`);
  });

  it("refuses text the server labelled as a different page", async () => {
    selectDocument(paper);
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === `/api/documents/${paper.id}/ask`) {
        return jsonResponse(answerWith([citations[0]]));
      }
      if (url === `/api/documents/${paper.id}/pages/4`) {
        return jsonResponse(pageText(paper.id, 2));
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const user = userEvent.setup();
    renderChat();

    await ask();
    await user.click(await screen.findByRole("button", { name: /page 4/i }));

    const viewer = await screen.findByRole("dialog", { name: "Page 4" });
    expect(await screen.findByRole("alert")).toHaveTextContent(/different page/i);
    expect(viewer).not.toHaveTextContent("Extracted text of page 2.");
  });

  it("dismisses the viewer with the Escape key", async () => {
    selectDocument(paper);
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === `/api/documents/${paper.id}/ask`) {
        return jsonResponse(answerWith(citations));
      }
      const pageMatch = /^\/api\/documents\/(\d+)\/pages\/(\d+)$/.exec(url);
      if (pageMatch !== null) {
        return jsonResponse(pageText(Number(pageMatch[1]), Number(pageMatch[2])));
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const user = userEvent.setup();
    renderChat();

    await ask();
    await user.click(await screen.findByRole("button", { name: /page 4/i }));
    await screen.findByRole("dialog", { name: "Page 4" });

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
