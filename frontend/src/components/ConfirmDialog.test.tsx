import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "./ConfirmDialog";

describe("ConfirmDialog", () => {
  it("is not visible when closed", () => {
    render(
      <ConfirmDialog open={false} title="Borrar usuario" description="¿Seguro?" onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.queryByText("Borrar usuario")).not.toBeVisible();
  });

  it("shows title/description and calls onConfirm/onCancel", async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    const user = userEvent.setup();

    render(
      <ConfirmDialog
        open
        title="Borrar usuario"
        description="Vas a borrar a carlos."
        confirmLabel="Borrar definitivamente"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );

    expect(screen.getByText("Borrar usuario")).toBeVisible();
    expect(screen.getByText("Vas a borrar a carlos.")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Borrar definitivamente" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("disables both buttons while busy", () => {
    render(
      <ConfirmDialog open title="Borrar usuario" description="…" busy onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Aplicando…" })).toBeDisabled();
  });
});
