import { expect, test, type Page } from "@playwright/test";

async function loginAsAdmin(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");
}

test("data catalog lists configured BC and Factorial tables with their key details", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/administracion/conexiones-api");

  await page.getByLabel("Nombre de la tabla").first().fill("bc_e2e_catalog");
  await page.getByLabel("URL de OData").fill("https://example.com/odata/Catalog");
  await page.getByLabel("Soporta extracción incremental (watermark)").first().check();
  await page.getByRole("button", { name: "Añadir tabla" }).first().click();
  await expect(page.getByText(/añadida/)).toBeVisible();

  await page.getByLabel("Nombre de la tabla").last().fill("factorial_e2e_catalog");
  await page.getByLabel("Ruta de la API (ej. resources/employees/employees)").fill("resources/e2e/catalog");
  await page.getByLabel("Campos a conservar (separados por comas)").fill("id, name");
  await page.getByRole("button", { name: "Añadir tabla" }).last().click();
  await expect(page.getByText(/añadida/)).toBeVisible();

  await page.goto("/catalogo-datos");
  await expect(page.getByRole("heading", { name: "Catálogo de datos" })).toBeVisible();

  const bcRow = page.locator("tr", { hasText: "bc_e2e_catalog" });
  await expect(bcRow).toContainText("https://example.com/odata/Catalog");
  await expect(bcRow).toContainText("Sí"); // incremental badge

  const factorialRow = page.locator("tr", { hasText: "factorial_e2e_catalog" });
  await expect(factorialRow).toContainText("resources/e2e/catalog");
  await expect(factorialRow).toContainText("id, name");

  // Clean up.
  await page.goto("/administracion/conexiones-api");
  await page.getByRole("button", { name: "Borrar tabla bc_e2e_catalog" }).click();
  await page.getByRole("button", { name: "Borrar definitivamente" }).click();
  await page.getByRole("button", { name: "Borrar tabla factorial_e2e_catalog" }).click();
  await page.getByRole("button", { name: "Borrar definitivamente" }).click();
});

test("history export link reflects the currently selected filters", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/actividad/historial");

  await page.getByLabel("Acción").selectOption("upload_factorial");
  const exportLink = page.getByRole("link", { name: "Exportar CSV" });
  await expect(exportLink).toHaveAttribute("href", /\/history\/export\.csv\?.*action=upload_factorial/);
});

test("audit export link reflects the currently selected filters", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/administracion/auditoria");

  await page.getByLabel("Evento").selectOption("login");
  const exportLink = page.getByRole("link", { name: "Exportar CSV" });
  await expect(exportLink).toHaveAttribute("href", /\/audit\/export\.csv\?.*event=login/);
});
