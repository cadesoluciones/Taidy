import { expect, test } from "@playwright/test";

test("operator can launch BC Sync and see it settle in Tareas en curso", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("operator1");
  await page.getByLabel("Contraseña", { exact: true }).fill("OperatorPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  await page.goto("/ejecutar/bc-sync");
  await page.getByRole("button", { name: "Ejecutar sync BC" }).click();
  await expect(page.getByText(/Tarea iniciada/)).toBeVisible();

  await page.goto("/actividad/tareas-en-curso");
  await expect(page.getByText("BC · Sync (extraer + subir)")).toBeVisible();
  await expect(page.getByText(/operator1 ·/)).toBeVisible();
});
