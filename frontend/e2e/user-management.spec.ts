import { expect, test } from "@playwright/test";

test("admin can create a user and change their role via the confirm dialog", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  await page.goto("/administracion/usuarios");
  await page.getByLabel("Usuario", { exact: true }).fill("carlos");
  await page.getByLabel("Contraseña temporal (mín. 8 caracteres)").fill("Temporal2026!");
  await page.getByRole("button", { name: "Crear usuario" }).click();
  await expect(page.getByText(/creado/)).toBeVisible();
  await expect(page.getByText("carlos", { exact: true })).toBeVisible();

  // H-04/ND-05: touching the role selector alone must not apply anything --
  // only reveal "Guardar rol", which then opens a confirmation dialog.
  await page.getByLabel("Rol de carlos").selectOption("App.Admin");
  const saveButton = page.getByRole("button", { name: "Guardar rol" });
  await expect(saveButton).toBeVisible();
  await saveButton.click();

  await expect(page.getByRole("heading", { name: "Cambiar rol" })).toBeVisible();
  await page.getByRole("button", { name: "Confirmar cambio" }).click();

  await expect(page.getByRole("heading", { name: "Cambiar rol" })).toHaveCount(0);
});
