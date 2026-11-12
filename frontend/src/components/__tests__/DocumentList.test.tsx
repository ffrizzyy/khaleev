import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import type { Document } from "../../types";
import { DocumentList } from "../DocumentList";

const first: Document = {
  id: 1,
  title: "First.pdf",
  page_count: 3,
  created_at: "2026-02-03T10:15:00Z",
};

const second: Document = {
  id: 2,
  title: "Second.pdf",
  page_count: 1,
  created_at: "2026-03-04T08:00:00Z",
};

const documents: Document[] = [first, second];

function renderList(overrides: Partial<ComponentProps<typeof DocumentList>> = {}) {
  const onSelect = vi.fn<(document: Document) => void>();
  const onDelete = vi.fn<(document: Document) => Promise<void>>().mockResolvedValue(undefined);
  render(
    <DocumentList
      documents={documents}
      selectedDocumentId={null}
      onSelect={onSelect}
      onDelete={onDelete}
      {...overrides}
    />,
  );
  return { onSelect, onDelete };
}

describe("DocumentList", () => {
  it("renders documents as a list with page count and ingest date", () => {
    renderList();

    const list = screen.getByRole("list");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(list).toContainElement(screen.getByText("First.pdf"));
    expect(screen.getByText("3 pages")).toBeInTheDocument();
    expect(screen.getByText("1 page")).toBeInTheDocument();
    expect(screen.getByText("2026-02-03")).toBeInTheDocument();
    expect(screen.getByText("2026-03-04")).toBeInTheDocument();
  });

  it("shows an empty state instead of an empty list", () => {
    renderList({ documents: [] });

    expect(screen.getByText(/no documents yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("marks the selected document and reports a newly selected one", async () => {
    const user = userEvent.setup();
    const { onSelect } = renderList({ selectedDocumentId: first.id });

    const rows = screen.getAllByRole("listitem");
    expect(rows[0]).toHaveAttribute("aria-current", "true");
    expect(rows[1]).not.toHaveAttribute("aria-current");
    expect(screen.getByText("Selected for Q&A")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Select Second.pdf" }));

    expect(onSelect).toHaveBeenCalledWith(second);
  });

  it("deletes only after the confirmation is accepted", async () => {
    const user = userEvent.setup();
    const { onDelete } = renderList();

    await user.click(screen.getByRole("button", { name: "Delete First.pdf" }));

    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.getByText(/delete "First.pdf"/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Confirm delete First.pdf" }));

    expect(onDelete).toHaveBeenCalledWith(first);
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Confirm delete First.pdf" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("cancels a pending deletion without calling the API", async () => {
    const user = userEvent.setup();
    const { onDelete } = renderList();

    await user.click(screen.getByRole("button", { name: "Delete First.pdf" }));
    await user.click(screen.getByRole("button", { name: "Cancel delete First.pdf" }));

    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Delete First.pdf" })).toBeInTheDocument();
  });

  it("renders a delete failure as a readable message and keeps the row", async () => {
    const user = userEvent.setup();
    const { onDelete } = renderList();
    onDelete.mockRejectedValueOnce(new ApiError(503, "The vector index is locked"));

    await user.click(screen.getByRole("button", { name: "Delete First.pdf" }));
    await user.click(screen.getByRole("button", { name: "Confirm delete First.pdf" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The vector index is locked");
    expect(screen.getByText("First.pdf")).toBeInTheDocument();
  });
});
