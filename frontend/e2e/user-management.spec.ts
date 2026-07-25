import { expect, test } from "@playwright/test";

test("admin can create a user and change their role via the confirm dialog", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  await page.goto("/administracion/usuarios");
  await page.getByLabel("Nuevo usuario").click();
  // Scoped to the create-user <form> -- the detail panel on the right also
  // has a (disabled) "Usuario" field for whichever account is selected.
  const createForm = page.locator("form").filter({ has: page.getByRole("button", { name: "Crear usuario" }) });
  await createForm.getByLabel("Usuario", { exact: true }).fill("carlos");
  await createForm.getByLabel("Contraseña temporal (mín. 8 caracteres)").fill("Temporal2026!");
  await createForm.getByRole("button", { name: "Crear usuario" }).click();
  await expect(page.getByText(/creado/)).toBeVisible();
  // Creating a user auto-selects it -- shows up both in the directory row
  // and as the detail panel's heading.
  await expect(page.getByRole("heading", { name: "carlos" })).toBeVisible();
  // H-04/ND-05: touching the role selector alone must not apply anything --
  // only enable "Guardar cambios", which then opens a confirmation dialog.
  await page.getByLabel("Rol", { exact: true }).selectOption("App.Admin");
  const saveButton = page.getByRole("button", { name: "Guardar cambios" });
  await expect(saveButton).toBeEnabled();
  await saveButton.click();

  await expect(page.getByRole("heading", { name: "Cambiar rol" })).toBeVisible();
  await page.getByRole("button", { name: "Confirmar cambio" }).click();

  await expect(page.getByRole("heading", { name: "Cambiar rol" })).toHaveCount(0);
});

test("admin can open Gestión de usuarios from the header icon on any page", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  await page.getByRole("button", { name: "Gestión de usuarios" }).click();
  await expect(page.getByRole("heading", { name: "Gestión de usuarios" })).toBeVisible();
  await expect(page.getByText("admin (tú)")).toBeVisible();

  await page.getByRole("button", { name: "Cerrar", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Gestión de usuarios" })).toHaveCount(0);
});
