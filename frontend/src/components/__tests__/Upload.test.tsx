import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Document } from "../../types";
import { Upload } from "../Upload";

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function makeFile(name: string, type: string): File {
  return new File(["%PDF-1.4"], name, { type });
}

const uploaded: Document = {
  id: 7,
  title: "Notes.pdf",
  page_count: 3,
  created_at: "2026-02-03T10:15:00Z",
};

const existing: Document = {
  id: 2,
  title: "Existing.pdf",
  page_count: 1,
  created_at: "2026-01-01T00:00:00Z",
};

function renderUpload(existingDocuments: readonly Document[] = []) {
  const onUploaded = vi.fn<(document: Document) => void>();
  render(<Upload existingDocuments={existingDocuments} onUploaded={onUploaded} />);
  return {
    onUploaded,
    input: screen.getByLabelText<HTMLInputElement>("Upload PDF"),
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Upload", () => {
  it("uploads a PDF as multipart and reports the new document", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(jsonResponse(uploaded, 201));
    const { input, onUploaded } = renderUpload();

    await user.upload(input, makeFile("Notes.pdf", "application/pdf"));

    expect(await screen.findByRole("status")).toHaveTextContent(/uploaded/i);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/documents");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBeInstanceOf(FormData);
    expect((init?.body as FormData).get("file")).toBeInstanceOf(File);
    expect(onUploaded).toHaveBeenCalledWith(uploaded);
  });

  it("shows a pending state while the upload is in flight", async () => {
    const user = userEvent.setup();
    let resolveUpload: (response: Response) => void = () => {};
    fetchMock.mockReturnValueOnce(
      new Promise<Response>((resolve) => {
        resolveUpload = resolve;
      }),
    );
    const { input } = renderUpload();

    await user.upload(input, makeFile("Notes.pdf", "application/pdf"));

    expect(await screen.findByRole("status")).toHaveTextContent(/uploading/i);
    expect(input).toBeDisabled();

    resolveUpload(jsonResponse(uploaded, 201));

    expect(await screen.findByText(/uploaded "Notes.pdf"/i)).toBeInTheDocument();
    expect(input).toBeEnabled();
  });

  it("renders an API failure as a readable message", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "The upload is not a PDF" }, 400));
    const { input, onUploaded } = renderUpload();

    await user.upload(input, makeFile("Scan.pdf", "application/pdf"));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The upload is not a PDF");
    expect(onUploaded).not.toHaveBeenCalled();
  });

  it("surfaces content-hash dedupe instead of reporting a second document", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(jsonResponse(existing, 200));
    const { input, onUploaded } = renderUpload([existing]);

    await user.upload(input, makeFile("Existing.pdf", "application/pdf"));

    expect(await screen.findByRole("status")).toHaveTextContent(/already in your library/i);
    expect(onUploaded).toHaveBeenCalledWith(existing);
  });

  it("rejects a non-PDF file before contacting the API", async () => {
    const user = userEvent.setup({ applyAccept: false });
    const { input } = renderUpload();

    await user.upload(input, makeFile("notes.txt", "text/plain"));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/not a PDF/i);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(input).toBeEnabled();
  });

  it("accepts a .pdf file whose MIME type is not reported", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(jsonResponse(uploaded, 201));
    const { input, onUploaded } = renderUpload();

    await user.upload(input, makeFile("Notes.pdf", ""));

    expect(onUploaded).toHaveBeenCalledWith(uploaded);
  });
});
