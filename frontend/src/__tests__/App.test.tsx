import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "../App";

describe("App", () => {
  it("renders the application name as a heading", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "Khaleev" })).toBeInTheDocument();
  });

  it("states the page-cited answer promise", () => {
    render(<App />);

    expect(screen.getByText(/page-cited answers/i)).toBeInTheDocument();
  });
});
