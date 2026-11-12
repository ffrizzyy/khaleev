import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AnswerResponse, Citation, Document } from "../../types";
import { AskPanel } from "../AskPanel";

const fetchMock = vi.fn<typeof fetch>();

const paper: Document = {
  id: 1,
  title: "Paper.pdf",
  page_count: 3,
  created_at: "2026-02-03T10:15:00Z",
};

const citation: Citation = {
  page: 4,
  quote: "flat 200 credit penalty per return",
};

const answer: AnswerResponse = {
  answer: "Late filings incur a flat 200 credit penalty per return.",
  citations: [citation],
};

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

function askCalls(): Array<Parameters<typeof fetch>> {
  return fetchMock.mock.calls.filter(
    ([input, init]) =>
      String(input) === `/api/documents/${paper.id}/ask` && (init?.method ?? "GET") === "POST",
  );
}

async function askQuestion(question = "What penalty applies to late filings?"): Promise<void> {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Question"), question);
  await user.click(screen.getByRole("button", { name: "Ask" }));
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AskPanel", () => {
  it("posts the question and renders the answer with one citation per source page", async () => {
    fetchMock.mockResolvedValue(jsonResponse(answer));
    const onOpenPage = vi.fn<(pageNumber: number) => void>();
    render(<AskPanel document={paper} onOpenPage={onOpenPage} />);

    await askQuestion();

    expect(await screen.findByText(answer.answer)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /page 4/i })).toBeInTheDocument();

    const calls = askCalls();
    expect(calls).toHaveLength(1);
    expect(JSON.parse(String(calls[0][1]?.body))).toEqual({
      question: "What penalty applies to late filings?",
    });
  });

  it("opens the cited page through the citation callback", async () => {
    fetchMock.mockResolvedValue(jsonResponse(answer));
    const user = userEvent.setup();
    const onOpenPage = vi.fn<(pageNumber: number) => void>();
    render(<AskPanel document={paper} onOpenPage={onOpenPage} />);

    await askQuestion();
    await user.click(await screen.findByRole("button", { name: /page 4/i }));

    expect(onOpenPage).toHaveBeenCalledWith(4);
  });

  it("does not call the API for a blank question", async () => {
    const user = userEvent.setup();
    render(<AskPanel document={paper} onOpenPage={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/enter a question/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("disables the question input while asking and never sends a second concurrent request", async () => {
    const pending = deferred<Response>();
    fetchMock.mockReturnValue(pending.promise);
    const { container } = render(<AskPanel document={paper} onOpenPage={vi.fn()} />);

    await askQuestion();

    const input = screen.getByLabelText("Question");
    expect(input).toBeDisabled();
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(/asking/i);
    expect(askCalls()).toHaveLength(1);

    const form = container.querySelector("form");
    expect(form).not.toBeNull();
    fireEvent.submit(form as HTMLFormElement);
    expect(askCalls()).toHaveLength(1);

    await act(async () => {
      pending.resolve(jsonResponse(answer));
    });

    expect(await screen.findByText(answer.answer)).toBeInTheDocument();
    expect(input).toBeEnabled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("explains an unreachable generator with its own message for a 503", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: "Could not reach the generator at http://localhost:11434" }, 503),
    );
    render(<AskPanel document={paper} onOpenPage={vi.fn()} />);

    await askQuestion();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/generator is unreachable/i);
    expect(alert).toHaveTextContent(/start ollama/i);
    expect(screen.queryByRole("button", { name: /page/i })).not.toBeInTheDocument();
  });

  it("explains a vanished document with its own message for a 404", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Document 1 does not exist" }, 404));
    render(<AskPanel document={paper} onOpenPage={vi.fn()} />);

    await askQuestion();

    expect(await screen.findByRole("alert")).toHaveTextContent(/no longer in the library/i);
  });

  it("explains an unindexed document with its own message for a 422", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: "document 1 has no indexed text to answer from" }, 422),
    );
    render(<AskPanel document={paper} onOpenPage={vi.fn()} />);

    await askQuestion();

    expect(await screen.findByRole("alert")).toHaveTextContent(/no indexed text/i);
  });

  it("reports an empty answer instead of rendering a blank result", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ answer: "   ", citations: [citation] }));
    render(<AskPanel document={paper} onOpenPage={vi.fn()} />);

    await askQuestion();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/empty answer/i);
  });

  it("renders the citation-defect state instead of a bare uncited answer", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ answer: "Late filings incur a penalty.", citations: [] }),
    );
    render(<AskPanel document={paper} onOpenPage={vi.fn()} />);

    await askQuestion();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/no page citations/i);
    expect(screen.queryByText("Late filings incur a penalty.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /page/i })).not.toBeInTheDocument();
  });
});
