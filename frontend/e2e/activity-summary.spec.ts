import { expect, test } from "@playwright/test";

test("admin can generate a template-based activity summary from Inicio", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  await page.goto("/");
  await expect(page.getByLabel("Plantilla")).toBeChecked();
  await page.getByRole("button", { name: "Generar" }).click();

  // Deliberately not launching a task here to generate history: every action
  // is already used elsewhere as either a real launch or an unused-control
  // value for another spec's filter assertions (see history-audit-filters.spec.ts),
  // and this test runs under the same parallel-worker history as everything
  // else anyway. build_template_summary() has a well-defined phrase for both
  // the empty and non-empty cases, so assert on whichever applies.
  await expect(page.getByText(/ejecuciones registradas|Todavía no se ha registrado ninguna ejecución/)).toBeVisible();
});

test("requesting the IA mode with no provider configured falls back to the template with a visible note", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  await page.goto("/");
  await page.getByLabel("IA generativa").check();
  await page.getByRole("button", { name: "Generar" }).click();

  await expect(page.getByText(/No hay un proveedor de IA configurado/)).toBeVisible();
});
