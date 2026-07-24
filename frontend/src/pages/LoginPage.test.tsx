import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { AuthProvider } from "../auth/AuthContext";
import { LoginPage } from "./LoginPage";

const { loginMock, fetchCurrentSessionMock } = vi.hoisted(() => ({
  loginMock: vi.fn(),
  fetchCurrentSessionMock: vi.fn(),
}));

vi.mock("../api/auth", () => ({
  login: loginMock,
  logout: vi.fn(),
  fetchCurrentSession: fetchCurrentSessionMock,
  changePassword: vi.fn(),
}));

function renderLoginPage() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  it("shows the server's error message when login fails", async () => {
    fetchCurrentSessionMock.mockRejectedValue(new ApiError(401, "No autenticado."));
    loginMock.mockRejectedValue(new ApiError(401, "Usuario o contraseña incorrectos."));
    const user = userEvent.setup();

    renderLoginPage();
    await user.type(screen.getByLabelText("Usuario"), "operator1");
    await user.type(screen.getByLabelText("Contraseña"), "wrong");
    await user.click(screen.getByRole("button", { name: "Acceder al panel" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Usuario o contraseña incorrectos.");
  });

  it("calls the login API with the entered credentials", async () => {
    fetchCurrentSessionMock.mockRejectedValue(new ApiError(401, "No autenticado."));
    loginMock.mockResolvedValue({ username: "operator1", role: "App.Operator", must_change_password: false });
    const user = userEvent.setup();

    renderLoginPage();
    await user.type(screen.getByLabelText("Usuario"), "operator1");
    await user.type(screen.getByLabelText("Contraseña"), "OperatorPass2026!");
    await user.click(screen.getByRole("button", { name: "Acceder al panel" }));

    await waitFor(() => expect(loginMock).toHaveBeenCalledWith("operator1", "OperatorPass2026!"));
  });

  it("toggles password visibility", async () => {
    fetchCurrentSessionMock.mockRejectedValue(new ApiError(401, "No autenticado."));
    const user = userEvent.setup();

    renderLoginPage();
    const passwordInput = screen.getByLabelText("Contraseña") as HTMLInputElement;
    expect(passwordInput.type).toBe("password");

    await user.click(screen.getByRole("button", { name: "Mostrar contraseña" }));
    expect(passwordInput.type).toBe("text");
  });
});
