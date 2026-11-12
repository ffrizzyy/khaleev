import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Citation } from "../../types";
import { CitationList } from "../CitationList";

const citations: Citation[] = [
  { page: 4, quote: "Late filings incur a flat 200 credit penalty per return." },
  { page: 7, quote: "The filing window closes on 31 March." },
];

describe("CitationList", () => {
  it("renders one button per citation, each naming its page number", () => {
    render(<CitationList citations={citations} onOpenPage={vi.fn()} />);

    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(2);
    expect(buttons[0]).toHaveAccessibleName(/page 4/i);
    expect(buttons[1]).toHaveAccessibleName(/page 7/i);
  });

  it("shows the supporting quote alongside each page reference", () => {
    render(<CitationList citations={citations} onOpenPage={vi.fn()} />);

    expect(screen.getByText(/flat 200 credit penalty per return/i)).toBeInTheDocument();
    expect(screen.getByText(/filing window closes on 31 march/i)).toBeInTheDocument();
  });

  it("reports the page number of the citation that was clicked", async () => {
    const user = userEvent.setup();
    const onOpenPage = vi.fn<(pageNumber: number) => void>();
    render(<CitationList citations={citations} onOpenPage={onOpenPage} />);

    await user.click(screen.getByRole("button", { name: /page 7/i }));

    expect(onOpenPage).toHaveBeenCalledTimes(1);
    expect(onOpenPage).toHaveBeenCalledWith(7);
  });

  it("marks the citation whose page is already open in the viewer", () => {
    render(<CitationList citations={citations} onOpenPage={vi.fn()} activePage={4} />);

    expect(screen.getByRole("button", { name: /page 4/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /page 7/i })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("renders nothing rather than an empty list when there are no citations", () => {
    const { container } = render(<CitationList citations={[]} onOpenPage={vi.fn()} />);

    expect(container).toBeEmptyDOMElement();
  });
});
