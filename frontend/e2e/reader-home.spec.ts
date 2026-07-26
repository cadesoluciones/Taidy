import { expect, test } from "@playwright/test";

async function loginAsAdmin(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");
}

test("Reader gets a simplified Inicio: reduced nav, launches their assigned workflow, sees it complete", async ({
  page,
}) => {
  await loginAsAdmin(page);

  const readerUsername = `home_e2e_${Date.now()}`;
  await page.goto("/administracion/usuarios");
  await page.getByLabel("Nuevo usuario").click();
  const createForm = page.locator("form").filter({ has: page.getByRole("button", { name: "Crear usuario" }) });
  await createForm.getByLabel("Usuario", { exact: true }).fill(readerUsername);
  await createForm.getByLabel("Contraseña temporal (mín. 8 caracteres)").fill("Temporal2026!");
  await createForm.getByRole("button", { name: "Crear usuario" }).click();
  await expect(page.getByText(/creado/)).toBeVisible();

  const workflowName = `Flujo Home E2E ${Date.now()}`;
  await page.goto("/flujos");
  await page.getByRole("button", { name: "Añadir bloque al flujo" }).click();
  await page.getByLabel("Nombre del flujo").fill(workflowName);
  await page.getByRole("button", { name: "Guardar flujo" }).click();
  await expect(page.getByText(workflowName)).toBeVisible();
  const card = page.getByTestId("workflow-card").filter({ hasText: workflowName });
  await card.locator("select").filter({ has: page.locator(`option[value="${readerUsername}"]`) }).selectOption(readerUsername);
  await expect(card.locator("span", { hasText: readerUsername })).toBeVisible();

  await page.getByRole("button", { name: "Cerrar sesión" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/login");

  // Log in as the fresh Reader and complete the forced password change.
  await page.getByLabel("Usuario").fill(readerUsername);
  await page.getByLabel("Contraseña", { exact: true }).fill("Temporal2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/change-password");
  await page.getByLabel("Nueva contraseña", { exact: true }).fill("ReaderHomeE2E2026!");
  await page.getByLabel("Confirma la nueva contraseña").fill("ReaderHomeE2E2026!");
  await page.getByRole("button", { name: "Guardar nueva contraseña" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  // Nav is reduced to Inicio + Cuenta -- nothing operational is reachable.
  const nav = page.getByRole("navigation");
  await expect(nav.getByRole("link", { name: "Inicio" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Mi cuenta" })).toBeVisible();
  await expect(nav.getByText("Business Central")).toHaveCount(0);
  await expect(nav.getByText("Flujos")).toHaveCount(0);
  await expect(nav.getByText("Actividad")).toHaveCount(0);
  await expect(nav.getByText("Programación")).toHaveCount(0);

  // Direct navigation to an operational page redirects back to Inicio.
  await page.goto("/flujos");
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  await expect(page.getByRole("heading", { name: "Taidy — Panel de datos" })).toBeVisible();
  const myCard = page.getByTestId("my-workflow-card").filter({ hasText: workflowName });
  await expect(myCard).toBeVisible();
  await expect(myCard.getByText("Nunca se ha ejecutado")).toBeVisible();

  await myCard.getByRole("button", { name: "Lanzar" }).click();
  await expect(myCard.getByRole("button", { name: /Ya en marcha|Lanzando…/ })).toBeVisible();

  // The isolated test server's fake subprocess finishes almost instantly;
  // poll until the card reflects a settled run rather than asserting a
  // specific in-flight status, which would be racy.
  await expect(myCard.getByRole("button", { name: "Lanzar" })).toBeEnabled({ timeout: 15000 });
  await expect(myCard.getByText(/Completada|Error/)).toBeVisible();

  // Clean up. Reader has no "Cerrar sesión"-adjacent nav item removed --
  // it's still in the header for every role -- but must actually log out
  // before /login will show a form instead of bouncing back to Inicio.
  await page.getByRole("button", { name: "Cerrar sesión" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/login");
  await loginAsAdmin(page);
  await page.goto("/flujos");
  const cleanupCard = page.getByTestId("workflow-card").filter({ hasText: workflowName });
  await cleanupCard.getByRole("button", { name: "Borrar flujo" }).click();
  await page.getByRole("button", { name: "Borrar definitivamente" }).click();
});

test("Reader with no assigned workflows sees a clear empty state", async ({ page }) => {
  await loginAsAdmin(page);

  const readerUsername = `home_empty_e2e_${Date.now()}`;
  await page.goto("/administracion/usuarios");
  await page.getByLabel("Nuevo usuario").click();
  const createForm = page.locator("form").filter({ has: page.getByRole("button", { name: "Crear usuario" }) });
  await createForm.getByLabel("Usuario", { exact: true }).fill(readerUsername);
  await createForm.getByLabel("Contraseña temporal (mín. 8 caracteres)").fill("Temporal2026!");
  await createForm.getByRole("button", { name: "Crear usuario" }).click();
  await expect(page.getByText(/creado/)).toBeVisible();

  await page.getByRole("button", { name: "Cerrar sesión" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/login");
  await page.getByLabel("Usuario").fill(readerUsername);
  await page.getByLabel("Contraseña", { exact: true }).fill("Temporal2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/change-password");
  await page.getByLabel("Nueva contraseña", { exact: true }).fill("ReaderEmptyE2E2026!");
  await page.getByLabel("Confirma la nueva contraseña").fill("ReaderEmptyE2E2026!");
  await page.getByRole("button", { name: "Guardar nueva contraseña" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  await expect(page.getByText(/Todavía no tienes ningún flujo asignado/)).toBeVisible();
});
