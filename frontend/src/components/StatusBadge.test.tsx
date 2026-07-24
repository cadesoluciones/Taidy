import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it.each([
    ["running", "En curso"],
    ["ok", "Completada"],
    ["error", "Error"],
    ["stopped", "Detenida"],
    ["in_progress", "En curso"],
  ])("renders the known label for status=%s", (status, expectedLabel) => {
    render(<StatusBadge status={status} />);
    expect(screen.getByText(expectedLabel)).toBeInTheDocument();
  });

  it("falls back to the raw status string for an unknown value instead of crashing", () => {
    render(<StatusBadge status="something_new" />);
    expect(screen.getByText("something_new")).toBeInTheDocument();
  });
});
