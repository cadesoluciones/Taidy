import { expect, test } from "@playwright/test";

test("admin can view and revoke a user's active session, logging them out", async ({ page, browser }) => {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  // A dedicated, never-reused username -- "operator1" is shared by many
  // other specs running in parallel and would carry lingering sessions from
  // those (nobody logs out at the end), making "exactly 1 session" flaky.
  const username = `sessions_e2e_${Date.now()}`;
  await page.goto("/administracion/usuarios");
  await page.getByLabel("Nuevo usuario").click();
  const createForm = page.locator("form").filter({ has: page.getByRole("button", { name: "Crear usuario" }) });
  await createForm.getByLabel("Usuario", { exact: true }).fill(username);
  await createForm.getByLabel("Contraseña temporal (mín. 8 caracteres)").fill("Temporal2026!");
  await createForm.getByRole("button", { name: "Crear usuario" }).click();
  await expect(page.getByText(/creado/)).toBeVisible();

  // A separate browser context = its own cookie jar, simulating this user
  // logged in from a different device/browser than the admin.
  const otherContext = await browser.newContext();
  const otherPage = await otherContext.newPage();
  await otherPage.goto("/login");
  await otherPage.getByLabel("Usuario").fill(username);
  await otherPage.getByLabel("Contraseña", { exact: true }).fill("Temporal2026!");
  await otherPage.getByRole("button", { name: "Acceder al panel" }).click();
  // Freshly-created users are forced through change-password before Inicio,
  // but the session itself already exists at this point.
  await expect(otherPage).toHaveURL("http://127.0.0.1:5173/change-password");

  await page.goto("/administracion/usuarios");
  await page.getByRole("button", { name: new RegExp(username) }).click();
  await expect(page.getByRole("heading", { name: username })).toBeVisible();

  const sessionRow = page.locator("li").filter({ hasText: "Iniciada:" });
  await expect(sessionRow).toHaveCount(1);
  await sessionRow.getByRole("button", { name: "Revocar sesión" }).click();
  await expect(page.getByText("Sin sesiones activas.")).toBeVisible();

  // The revocation is real, not just a UI list update -- this user's actual
  // browser session must now be logged out server-side.
  await otherPage.reload();
  await expect(otherPage).toHaveURL("http://127.0.0.1:5173/login");

  await otherContext.close();
});
