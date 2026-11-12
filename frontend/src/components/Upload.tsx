/**
 * PDF upload control (F1): a labelled file input that posts multipart to
 * `/api/documents` and reports every outcome in one live region.
 *
 * The backend dedupes by content hash and answers a repeated file with the
 * *existing* document (200 instead of 201). That distinction is not exposed by
 * the typed client, so the control compares the returned id with the documents
 * already on the page: a match means dedupe, which is reported as such instead
 * of pretending a second copy was ingested.
 *
 * Non-PDF files are rejected locally before any request is made, because a
 * 400 from the server is a worse experience than an immediate, specific
 * message. The input stays enabled after every outcome so a retry is one
 * keystroke away.
 */

import { useId, useState } from "react";
import type { ChangeEvent, ReactElement } from "react";

import { isApiError } from "../api/client";
import { uploadDocument } from "../api/documents";
import type { Document } from "../types";

const PDF_MIME_TYPE = "application/pdf";

type UploadStatus =
  | { kind: "idle" }
  | { kind: "uploading"; fileName: string }
  | { kind: "success"; message: string }
  | { kind: "error"; message: string };

export interface UploadProps {
  /** The documents currently listed, used to recognise a deduped upload. */
  existingDocuments?: readonly Document[];
  /** Called after the server accepted the file, so the caller can refresh. */
  onUploaded: (document: Document) => void;
}

/** A PDF is detected by MIME type, extension, or both (some OSes omit the type). */
function isPdfFile(file: File): boolean {
  return file.type === PDF_MIME_TYPE || file.name.toLowerCase().endsWith(".pdf");
}

function pagesLabel(pageCount: number): string {
  return `${pageCount} ${pageCount === 1 ? "page" : "pages"}`;
}

function describeFailure(error: unknown): string {
  if (isApiError(error)) {
    return error.detail;
  }
  return error instanceof Error ? error.message : "Unknown error";
}

function statusMessage(status: UploadStatus): string {
  switch (status.kind) {
    case "idle":
      return "";
    case "uploading":
      return `Uploading "${status.fileName}"…`;
    case "success":
    case "error":
      return status.message;
  }
}

export function Upload({ existingDocuments = [], onUploaded }: UploadProps): ReactElement {
  const inputId = useId();
  const descriptionId = useId();
  const [status, setStatus] = useState<UploadStatus>({ kind: "idle" });
  const uploading = status.kind === "uploading";

  async function uploadFile(file: File): Promise<void> {
    if (!isPdfFile(file)) {
      setStatus({
        kind: "error",
        message: `"${file.name}" is not a PDF. Choose a PDF file.`,
      });
      return;
    }

    setStatus({ kind: "uploading", fileName: file.name });
    try {
      const document = await uploadDocument(file);
      const duplicate = existingDocuments.some((existing) => existing.id === document.id);
      setStatus({
        kind: "success",
        message: duplicate
          ? `"${file.name}" was already in your library as "${document.title}". Nothing was uploaded twice.`
          : `Uploaded "${document.title}" (${pagesLabel(document.page_count)}).`,
      });
      onUploaded(document);
    } catch (error) {
      setStatus({ kind: "error", message: `Upload failed: ${describeFailure(error)}` });
    }
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>): void {
    const file = event.currentTarget.files?.[0];
    // Clear the input so choosing the same file again still fires a change.
    event.currentTarget.value = "";
    if (file !== undefined) {
      void uploadFile(file);
    }
  }

  return (
    <section aria-labelledby={`${inputId}-heading`} aria-busy={uploading}>
      <h3 id={`${inputId}-heading`}>Upload a PDF</h3>
      <label htmlFor={inputId}>Upload PDF</label>
      <input
        id={inputId}
        type="file"
        accept="application/pdf,.pdf"
        aria-describedby={descriptionId}
        disabled={uploading}
        onChange={handleChange}
      />
      <p id={descriptionId}>Pick a PDF from your machine. It is stored locally.</p>
      {status.kind !== "idle" ? (
        <p role={status.kind === "error" ? "alert" : "status"}>{statusMessage(status)}</p>
      ) : null}
    </section>
  );
}
