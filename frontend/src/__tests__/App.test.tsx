import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { App } from "../App";

afterEach(() => {
  window.history.pushState({}, "", "/");
});

describe("App", () => {
  it("renders the application name as a heading", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "Khaleev" })).toBeInTheDocument();
  });

  it("states the page-cited answer promise", () => {
    render(<App />);

    expect(screen.getByText(/page-cited answers/i)).toBeInTheDocument();
  });

  it("links to the three routes of the app shell", () => {
    render(<App />);

    expect(screen.getByRole("link", { name: "Library" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute("href", "/chat");
    expect(screen.getByRole("link", { name: "Eval dashboard" })).toHaveAttribute("href", "/evals");
  });

  it("renders the library at /", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "Library" })).toBeInTheDocument();
  });

  it("renders the chat page at /chat", () => {
    window.history.pushState({}, "", "/chat");

    render(<App />);

    expect(screen.getByRole("heading", { name: "Chat" })).toBeInTheDocument();
  });

  it("renders the eval dashboard at /evals", () => {
    window.history.pushState({}, "", "/evals");

    render(<App />);

    expect(screen.getByRole("heading", { name: "Eval dashboard" })).toBeInTheDocument();
  });

  it("navigates between routes through the primary navigation", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("link", { name: "Chat" }));

    expect(screen.getByRole("heading", { name: "Chat" })).toBeInTheDocument();
  });

  it("renders a not-found page for an unknown route", () => {
    window.history.pushState({}, "", "/nope");

    render(<App />);

    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});
