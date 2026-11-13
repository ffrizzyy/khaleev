/**
 * The ask panel (F3, AC2): ask one question about the selected document and
 * render the page-cited answer.
 *
 * Every failure mode gets its own sentence, because "request failed" is useless
 * when the cause is one of three very different things: the generator is down
 * (503), the document disappeared (404), or it has no indexed text (422). An
 * empty answer and an answer with no citations are separate defect states —
 * the product promise is that an answer never ships without page references
 * (Locked intent #4), so an uncited answer is reported as a defect instead of
 * being displayed as if it were trustworthy.
 *
 * Concurrency is guarded twice: the input and button are disabled while asking,
 * and a ref flips synchronously on submit so even a programmatic double submit
 * cannot start a second request.
 */

import { useId, useRef, useState } from "react";
import type { FormEvent, ReactElement } from "react";

import { isApiError } from "../api/client";
import { askDocument } from "../api/documents";
import type { AnswerResponse, Document } from "../types";
import { CitationList } from "./CitationList";

type AskState =
  | { kind: "idle" }
  | { kind: "asking"; question: string }
  | { kind: "answered"; question: string; response: AnswerResponse }
  | { kind: "failed"; message: string };

export interface AskPanelProps {
  /** The selected document; the question is scoped to it on the server too. */
  document: Document;
  /** Opens the page viewer at a citation's 1-based page number. */
  onOpenPage: (pageNumber: number) => void;
  /** The page currently open in the viewer, highlighted in the citation list. */
  activePage?: number | null;
}

function describeAskFailure(error: unknown): string {
  if (isApiError(error)) {
    switch (error.status) {
      case 404:
        return "That document is no longer in the library. Pick another document or upload the PDF again.";
      case 422:
        return "This document has no indexed text to answer from. Delete and re-upload the PDF, then ask again.";
      case 503:
        return "The answer generator is unreachable. Start Ollama (or configure a generator) and try again.";
      default:
        return `Could not get an answer: ${error.detail}`;
    }
  }
  if (error instanceof Error) {
    return `Could not get an answer: ${error.message}`;
  }
  return "Could not get an answer.";
}

export function AskPanel({ document, onOpenPage, activePage = null }: AskPanelProps): ReactElement {
  const inputId = useId();
  const hintId = useId();
  const answerHeadingId = useId();
  const [question, setQuestion] = useState("");
  const [state, setState] = useState<AskState>({ kind: "idle" });
  const inFlight = useRef(false);
  const asking = state.kind === "asking";

  async function ask(): Promise<void> {
    if (inFlight.current) {
      return;
    }
    const trimmed = question.trim();
    if (trimmed.length === 0) {
      setState({ kind: "failed", message: "Enter a question before asking." });
      return;
    }

    inFlight.current = true;
    setState({ kind: "asking", question: trimmed });
    try {
      const response = await askDocument(document.id, trimmed);
      setState({ kind: "answered", question: trimmed, response });
    } catch (error) {
      setState({ kind: "failed", message: describeAskFailure(error) });
    } finally {
      inFlight.current = false;
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    void ask();
  }

  function renderOutcome(): ReactElement | null {
    if (state.kind === "failed") {
      return (
        <p className="alert" role="alert">
          {state.message}
        </p>
      );
    }
    if (state.kind !== "answered") {
      return null;
    }
    const { response } = state;

    if (response.answer.trim().length === 0) {
      return (
        <p className="alert" role="alert">
          The generator returned an empty answer. Try rephrasing the question, or check that the
          generator is running.
        </p>
      );
    }

    if (response.citations.length === 0) {
      return (
        <p className="alert" role="alert">
          This answer has no page citations, so it cannot be trusted. Ask again, or delete and
          re-upload the document so its pages are indexed.
        </p>
      );
    }

    return (
      <section className="answer" aria-labelledby={answerHeadingId}>
        <h4 className="answer__heading" id={answerHeadingId}>
          Answer
        </h4>
        <p className="answer__question">Question: {state.question}</p>
        <p className="answer__body">{response.answer}</p>
        <CitationList
          citations={response.citations}
          onOpenPage={onOpenPage}
          activePage={activePage}
        />
      </section>
    );
  }

  return (
    <section className="panel panel--ask" aria-labelledby={`${inputId}-heading`} aria-busy={asking}>
      <h3 className="panel__title" id={`${inputId}-heading`}>
        Ask a question
      </h3>
      <form className="ask-form" onSubmit={handleSubmit}>
        <label className="field__label" htmlFor={inputId}>
          Question
        </label>
        <input
          className="field__text"
          id={inputId}
          type="text"
          value={question}
          disabled={asking}
          aria-describedby={hintId}
          onChange={(event) => setQuestion(event.currentTarget.value)}
        />
        <p className="field__hint" id={hintId}>
          The answer uses only page-attributed text from this document, and every answer cites its
          source pages.
        </p>
        <button className="button button--primary" type="submit" disabled={asking}>
          Ask
        </button>
      </form>
      {asking ? (
        <p className="status" role="status">
          Asking the selected document…
        </p>
      ) : null}
      {renderOutcome()}
    </section>
  );
}
