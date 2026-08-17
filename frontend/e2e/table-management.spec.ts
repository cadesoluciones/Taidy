import { expect, test, type Page } from "@playwright/test";

async function loginAsAdmin(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");
}

test("admin can add a new Business Central table from the Conexiones API page", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/administracion/conexiones-api");

  await page.getByLabel("Nombre de la tabla").first().fill("bc_e2e_new_table");
  await page.getByLabel("URL de OData").fill("https://example.com/odata/NewTable");
  await page.getByLabel("Descripción (opcional)").first().fill("Tabla de prueba E2E");
  await page.getByRole("button", { name: "Añadir tabla" }).first().click();

  await expect(page.getByText(/añadida/)).toBeVisible();
  await expect(page.locator("li", { hasText: "bc_e2e_new_table" })).toBeVisible();

  // The BC extract form's own table selector must pick it up too. Options
  // inside a closed native <select> report as "hidden" in Playwright even
  // though they're valid choices, so assert on text content, not visibility.
  await page.goto("/ejecutar/bc-extraer");
  await expect(page.locator("#tables")).toContainText("bc_e2e_new_table");

  // Clean up via the delete button so this test can run again against the
  // same long-lived isolated server without a duplicate-name conflict.
  await page.goto("/administracion/conexiones-api");
  await page.getByRole("button", { name: "Borrar tabla bc_e2e_new_table" }).click();
  await page.getByRole("button", { name: "Borrar definitivamente" }).click();
  await expect(page.locator("li", { hasText: "bc_e2e_new_table" })).toHaveCount(0);
});

test("admin can edit an existing Business Central table", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/administracion/conexiones-api");

  await page.getByLabel("Nombre de la tabla").first().fill("bc_e2e_edit_table");
  await page.getByLabel("URL de OData").fill("https://example.com/odata/Original");
  await page.getByRole("button", { name: "Añadir tabla" }).first().click();
  await expect(page.getByText(/añadida/)).toBeVisible();

  await page.getByRole("button", { name: "Editar tabla bc_e2e_edit_table" }).click();
  // The name field is locked while editing -- renaming isn't supported.
  await expect(page.getByLabel("Nombre de la tabla").first()).toBeDisabled();
  await page.getByLabel("URL de OData").fill("https://example.com/odata/Updated");
  await page.getByLabel("Descripción (opcional)").first().fill("Editada por E2E");
  await page.getByRole("button", { name: "Guardar cambios" }).first().click();

  await expect(page.getByText(/actualizada/)).toBeVisible();
  await expect(page.locator("li", { hasText: "bc_e2e_edit_table" }).getByText("Editada por E2E")).toBeVisible();

  // Clean up.
  await page.getByRole("button", { name: "Borrar tabla bc_e2e_edit_table" }).click();
  await page.getByRole("button", { name: "Borrar definitivamente" }).click();
  await expect(page.locator("li", { hasText: "bc_e2e_edit_table" })).toHaveCount(0);
});

test("admin can add a new Factorial table requiring at least one field", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/administracion/conexiones-api");

  // Submitting without any field must be rejected client-side.
  await page.getByLabel("Nombre de la tabla").last().fill("factorial_e2e_new");
  await page.getByLabel("Ruta de la API (ej. resources/employees/employees)").fill("resources/e2e/new");
  await page.getByRole("button", { name: "Añadir tabla" }).last().click();
  await expect(page.getByText(/al menos un campo/)).toBeVisible();

  await page.getByLabel("Campos a conservar (separados por comas)").fill("id, name");
  await page.getByRole("button", { name: "Añadir tabla" }).last().click();

  await expect(page.getByText(/añadida/)).toBeVisible();
  await expect(page.locator("li", { hasText: "factorial_e2e_new" })).toBeVisible();

  await page.goto("/ejecutar/factorial-extraer");
  await expect(page.locator("#tables")).toContainText("factorial_e2e_new");

  await page.goto("/administracion/conexiones-api");
  await page.getByRole("button", { name: "Borrar tabla factorial_e2e_new" }).click();
  await page.getByRole("button", { name: "Borrar definitivamente" }).click();
  await expect(page.locator("li", { hasText: "factorial_e2e_new" })).toHaveCount(0);
});

test("admin can edit an existing Factorial table", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/administracion/conexiones-api");

  await page.getByLabel("Nombre de la tabla").last().fill("factorial_e2e_edit");
  await page.getByLabel("Ruta de la API (ej. resources/employees/employees)").fill("resources/e2e/original");
  await page.getByLabel("Campos a conservar (separados por comas)").fill("id");
  await page.getByRole("button", { name: "Añadir tabla" }).last().click();
  await expect(page.getByText(/añadida/)).toBeVisible();

  await page.getByRole("button", { name: "Editar tabla factorial_e2e_edit" }).click();
  await expect(page.getByLabel("Nombre de la tabla").last()).toBeDisabled();
  await page.getByLabel("Ruta de la API (ej. resources/employees/employees)").fill("resources/e2e/updated");
  await page.getByLabel("Campos a conservar (separados por comas)").fill("id, name, email");
  await page.getByRole("button", { name: "Guardar cambios" }).last().click();

  await expect(page.getByText(/actualizada/)).toBeVisible();

  // Clean up.
  await page.getByRole("button", { name: "Borrar tabla factorial_e2e_edit" }).click();
  await page.getByRole("button", { name: "Borrar definitivamente" }).click();
  await expect(page.locator("li", { hasText: "factorial_e2e_edit" })).toHaveCount(0);
});

test("operator is redirected away from Conexiones API and sees no manage-tables link", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("operator1");
  await page.getByLabel("Contraseña", { exact: true }).fill("OperatorPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  await page.goto("/administracion/conexiones-api");
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  for (const path of ["/ejecutar/bc-extraer", "/ejecutar/bc-sync", "/ejecutar/factorial-extraer", "/ejecutar/factorial-subir", "/ejecutar/factorial-sync"]) {
    await page.goto(path);
    await expect(page.getByRole("link", { name: "Gestionar tablas" })).toHaveCount(0);
  }
});

test("admin sees a 'Gestionar tablas' link on every form with a table picker", async ({ page }) => {
  await loginAsAdmin(page);
  for (const path of [
    "/ejecutar/bc-extraer",
    "/ejecutar/bc-sync",
    "/ejecutar/factorial-extraer",
    "/ejecutar/factorial-subir",
    "/ejecutar/factorial-sync",
  ]) {
    await page.goto(path);
    await expect(page.getByRole("link", { name: "Gestionar tablas" })).toBeVisible();
  }
});

test("table selector shows picked tables as removable tags instead of a native multiselect", async ({ page }) => {
  await loginAsAdmin(page);

  // Seed a table of our own rather than relying on ambient state from other
  // tests -- specs run in parallel, so nothing guarantees one exists yet.
  await page.goto("/administracion/conexiones-api");
  await page.getByLabel("Nombre de la tabla").first().fill("bc_e2e_tag_table");
  await page.getByLabel("URL de OData").fill("https://example.com/odata/TagTable");
  await page.getByRole("button", { name: "Añadir tabla" }).first().click();
  await expect(page.getByText(/añadida/)).toBeVisible();

  await page.goto("/ejecutar/bc-extraer");
  const addSelect = page.locator("#tables");
  await addSelect.selectOption("bc_e2e_tag_table");

  // Picking a table shows it as a tag with a remove button -- the whole
  // point being that a native <select multiple> gives no visible way to
  // deselect, whereas a tag can just be removed with one click.
  const tag = page.locator("span", { hasText: "bc_e2e_tag_table" }).filter({ has: page.getByRole("button") });
  await expect(tag).toBeVisible();
  // The picked table is no longer offered again in the "add" dropdown.
  await expect(addSelect.locator("option", { hasText: "bc_e2e_tag_table" })).toHaveCount(0);

  await tag.getByRole("button").click();
  await expect(tag).toHaveCount(0);
  // Removing it makes it selectable again.
  await expect(addSelect.locator("option", { hasText: "bc_e2e_tag_table" })).toHaveCount(1);

  // Clean up.
  await page.goto("/administracion/conexiones-api");
  await page.getByRole("button", { name: "Borrar tabla bc_e2e_tag_table" }).click();
  await page.getByRole("button", { name: "Borrar definitivamente" }).click();
});

test("sidebar groups Business Central and Factorial actions into separate sections", async ({ page }) => {
  await loginAsAdmin(page);
  const nav = page.getByRole("navigation");
  await expect(nav.getByText("Business Central")).toBeVisible();
  await expect(nav.getByText("Factorial")).toBeVisible();
  await expect(nav.getByText("Fabric")).toBeVisible();

  // Multi-item sections start collapsed (see NavShell's collapsible-sidebar
  // groups) unless the current page lives inside one -- Home doesn't, so
  // both need an explicit expand before their links become visible.
  await nav.getByRole("button", { name: /Business Central/ }).click();
  const bcSection = nav.getByText("Business Central").locator("..");
  await expect(bcSection.getByRole("link", { name: "Extraer" })).toBeVisible();

  await nav.getByRole("button", { name: /Administración/ }).click();
  await expect(nav.getByRole("link", { name: "Conexiones API" })).toBeVisible();
});
