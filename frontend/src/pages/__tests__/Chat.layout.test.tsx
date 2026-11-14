/**
 * Layout coverage for the T24 Chat page: the document context strip, the three
 * ask cards and the page viewer card.
 *
 * Structure, roles and text only — never a class name. Document order is the
 * property that makes the R1 columns stack correctly at narrow widths, so the
 * assertions below compare the nodes' positions instead of their styling.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearSelectedDocument,
  rememberDocuments,
  selectDocument,
} from "../../state/selectedDocument";
import type { AnswerResponse, Citation, Document } from "../../types";
import { Chat } from "../Chat";

const fetchMock = vi.fn<typeof fetch>();

const paper: Document = {
  id: 1,
  title: "Paper.pdf",
  page_count: 8,
  created_at: "2026-02-03T10:15:00Z",
};

/** A live document the app knows about; not the persisted Q&A target. */
const other: Document = {
  id: 2,
  title: "Other.pdf",
  page_count: 1,
  created_at: "2026-03-04T08:00:00Z",
};

/** A realistic long title: no card may clip it or push its track wider. */
const longTitle =
  "International taxation of cross-border professional services and the late-filing " +
  "penalty regime for multinational partnerships, consolidated edition.pdf";

/** A realistic long answer: a whole paragraph in one text node. */
const longAnswer =
  "Late filings incur a flat 200 credit penalty per return, payable within thirty days of the " +
  "assessment notice. Where the filer is a partnership, the penalty is assessed against the " +
  "partnership and not against the individual partners, and a second or subsequent late filing " +
  "in the same tax year doubles the penalty up to a ceiling of 1000 credits. Filing before the " +
  "due date but after the extended deadline still attracts the flat penalty, though interest is " +
  "not charged; the assessment notice names the page the penalty rule was read from so the " +
  "filer can verify the calculation against the original filing.";

const citations: Citation[] = [
  { page: 123, quote: "flat 200 credit penalty per return" },
  { page: 4, quote: "the partnership is assessed, not the partners" },
];

const answer: AnswerResponse = { answer: longAnswer, citations };

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function pageText(documentId: number, pageNumber: number): unknown {
  return {
    document_id: documentId,
    page_number: pageNumber,
    text: `Extracted text of page ${pageNumber}.`,
  };
}

function installAskApi(): void {
  fetchMock.mockImplementation(async (input) => {
    const url = String(input);
    if (url === `/api/documents/${paper.id}/ask`) {
      return jsonResponse(answer);
    }
    const pageMatch = /^\/api\/documents\/(\d+)\/pages\/(\d+)$/.exec(url);
    if (pageMatch !== null) {
      return jsonResponse(pageText(Number(pageMatch[1]), Number(pageMatch[2])));
    }
    throw new Error(`Unexpected request: ${url}`);
  });
}

/** True when `first` comes before `second` in document order. */
function precedes(first: Element, second: Element): boolean {
  const position = first.compareDocumentPosition(second);
  return (position & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
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

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  clearSelectedDocument();
  sessionStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Chat layout", () => {
  it("keeps the document title and the page count as separate context-strip elements", () => {
    selectDocument(paper);
    installAskApi();
    renderChat();

    const strip = screen.getByRole("region", { name: "Selected document" });
    const title = within(strip).getByText(/questioning Paper\.pdf/i);
    const pageCount = within(strip).getByText("8 pages");

    // Two distinct nodes: the title is never merged into the page count.
    expect(title).not.toBe(pageCount);
    expect(title.textContent).toMatch(/questioning Paper\.pdf/i);
    expect(pageCount.textContent).toBe("8 pages");
  });

  it("links the context strip back to the Library", () => {
    selectDocument(paper);
    installAskApi();
    renderChat();

    const strip = screen.getByRole("region", { name: "Selected document" });
    expect(within(strip).getByRole("link", { name: /back to the library/i })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("renders the question form, the answer and the citations as three named cards before the viewer", async () => {
    selectDocument(paper);
    installAskApi();
    const user = userEvent.setup();
    renderChat();

    const askCard = screen.getByRole("region", { name: "Ask a question" });
    expect(screen.queryByRole("region", { name: "Answer" })).not.toBeInTheDocument();

    await ask();

    const answerCard = await screen.findByRole("region", { name: "Answer" });
    const citationCard = screen.getByRole("region", { name: "Citations" });

    expect(precedes(askCard, answerCard)).toBe(true);
    expect(precedes(answerCard, citationCard)).toBe(true);

    await user.click(within(citationCard).getByRole("button", { name: "Page 4" }));

    const viewer = await screen.findByRole("dialog", { name: "Page 4" });
    // The viewer is its own card after the three ask cards, so stacking the
    // columns at narrow widths puts it directly below the answer.
    expect(precedes(citationCard, viewer)).toBe(true);
  });

  it("keeps a long title, a long answer and a three-digit page reference intact", async () => {
    const longPaper: Document = { ...paper, title: longTitle, page_count: 123 };
    selectDocument(longPaper);
    installAskApi();
    renderChat();

    expect(screen.getByText(longTitle, { exact: false })).toBeInTheDocument();
    expect(screen.getByText("123 pages").textContent).toBe("123 pages");

    await ask();

    expect(await screen.findByText(longAnswer)).toBeInTheDocument();

    const chip = screen.getByRole("button", { name: "Page 123" });
    expect(chip).toHaveTextContent("Page 123");
    expect(chip).toHaveAttribute("aria-pressed", "false");

    const user = userEvent.setup();
    await user.click(chip);

    expect(await screen.findByRole("dialog", { name: "Page 123" })).toBeInTheDocument();
  });

  it("opens no viewer card until a citation is activated", () => {
    selectDocument(paper);
    installAskApi();
    renderChat();

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps the empty state as a named page with a route to the Library", () => {
    renderChat();

    expect(screen.getByRole("heading", { name: "Chat" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /library/i })).toHaveAttribute("href", "/");
    expect(screen.queryByRole("region", { name: "Selected document" })).not.toBeInTheDocument();
  });

  it("discards a persisted selection the recorded list no longer contains, without a request", () => {
    // The Library published the list earlier; the persisted id is not in it.
    rememberDocuments([other]);
    selectDocument(paper);
    renderChat();

    expect(screen.getByRole("heading", { name: "Chat" })).toBeInTheDocument();
    expect(screen.getByText(/no document selected/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /library/i })).toHaveAttribute("href", "/");
    expect(screen.queryByText(/questioning/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Selected document" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Question")).not.toBeInTheDocument();
    // A deleted document is not an error, and reconciling never fetches the list.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(/does not exist/i)).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
