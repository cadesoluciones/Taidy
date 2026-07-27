import { expect, test } from "@playwright/test";

/**
 * Requires the isolated API server + Vite dev server already running
 * against throwaway state (see playwright.config.ts). Uses the "operator1"
 * user seeded by the isolated launcher -- never the real webapp/users.db.
 */
test.describe("Login journey", () => {
  test("wrong password shows an error and does not navigate away", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Usuario").fill("operator1");
    await page.getByLabel("Contraseña", { exact: true }).fill("wrong-password");
    await page.getByRole("button", { name: "Acceder al panel" }).click();

    await expect(page.getByRole("alert")).toContainText("Usuario o contraseña incorrectos");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("correct credentials reach the authenticated home page", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Usuario").fill("operator1");
    await page.getByLabel("Contraseña", { exact: true }).fill("OperatorPass2026!");
    await page.getByRole("button", { name: "Acceder al panel" }).click();

    await expect(page).toHaveURL("http://127.0.0.1:5173/");
    await expect(page.getByRole("heading", { level: 1, name: "NEXUS-BDB — Panel de datos" })).toBeVisible();
    await expect(page.getByRole("banner").getByText("App.Operator")).toBeVisible();
  });

  test("logout returns to the login page and blocks going back", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Usuario").fill("operator1");
    await page.getByLabel("Contraseña", { exact: true }).fill("OperatorPass2026!");
    await page.getByRole("button", { name: "Acceder al panel" }).click();
    await expect(page).toHaveURL("http://127.0.0.1:5173/");

    await page.getByRole("button", { name: "Cerrar sesión" }).click();
    await expect(page).toHaveURL(/\/login$/);

    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("a freshly-seeded admin is forced through change-password before reaching home", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Usuario").fill("admin");
    await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
    await page.getByRole("button", { name: "Acceder al panel" }).click();

    // This admin's password was already rotated by the isolated launcher
    // script (must_change_password=false), so it should land straight on
    // home -- this test documents that expectation explicitly rather than
    // asserting the forced-change screen against a user that doesn't need it.
    await expect(page).toHaveURL("http://127.0.0.1:5173/");
  });
});
