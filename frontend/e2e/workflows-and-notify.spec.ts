import { expect, test } from "@playwright/test";

test("admin can design a workflow, then edit its name and steps", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  await page.goto("/flujos");
  await page.getByRole("button", { name: "Editor" }).click();
  await page.getByRole("button", { name: "Añadir bloque al flujo" }).click();
  await expect(page.getByLabel("Etiqueta del bloque seleccionado")).toHaveValue("Bloque 1");
  await page.getByLabel("Etiqueta del bloque seleccionado").fill("Paso inicial");

  const workflowName = `Flujo E2E ${Date.now()}`;
  await page.getByLabel("Nombre del flujo").fill(workflowName);
  await page.getByRole("button", { name: "Guardar flujo" }).click();
  await expect(page.getByText(workflowName)).toBeVisible();

  const savedCard = page
    .locator("div")
    .filter({ hasText: workflowName })
    .filter({ has: page.getByRole("button", { name: "Editar flujo" }) })
    .last();
  await savedCard.getByRole("button", { name: "Editar flujo" }).click();
  await expect(page.getByRole("heading", { name: "Editar flujo guardado" })).toBeVisible();
  const nameInput = page.getByLabel("Nombre del flujo");
  await expect(nameInput).toHaveValue(workflowName);
  const renamedTo = `${workflowName} renombrado`;
  await nameInput.fill(renamedTo);

  await page.getByRole("button", { name: "Añadir bloque al flujo" }).click();
  await page.getByRole("button", { name: "Guardar cambios" }).click();

  await expect(page.getByText(renamedTo)).toBeVisible();
  const renamedCard = page.locator("div").filter({ hasText: renamedTo }).last();
  await expect(renamedCard.getByText("2 bloque(s)")).toBeVisible();
});

test("notify checkbox is present and controllable on a task launch form", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("operator1");
  await page.getByLabel("Contraseña", { exact: true }).fill("OperatorPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  // Uses a Factorial action (not BC) so this doesn't race task-launch.spec.ts's
  // concurrent sync_bc launch -- both would land in the same BC conflict
  // group in webapp/tasks.py's _CONFLICT_GROUPS under parallel workers.
  await page.goto("/ejecutar/factorial-subir");
  const notifyCheckbox = page.getByRole("checkbox", { name: /Avisar por email/ });
  await expect(notifyCheckbox).toBeVisible();
  await expect(notifyCheckbox).not.toBeChecked();
  await notifyCheckbox.check();
  await expect(notifyCheckbox).toBeChecked();

  await page.getByRole("button", { name: "Ejecutar subida Factorial" }).click();
  await expect(page.getByText(/Tarea iniciada/)).toBeVisible();
});
