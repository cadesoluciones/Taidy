import { expect, test, type Page } from "@playwright/test";

async function loginAsAdmin(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");
}

test("scheduling a Factorial extract collects a start date (previously missing entirely)", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/programacion");

  await page.getByLabel("Nombre de la tarea").fill("Nightly Factorial extract");
  await page.getByLabel("Acción a programar").selectOption("extract_factorial");

  // The start-date field (and its "Hasta se calcula solo" explanation) only
  // appear once Factorial is selected -- this is exactly the field that was
  // silently missing before, which made every such schedule fail at
  // execution time ("'Desde' y 'Hasta' son obligatorios para Factorial").
  await expect(page.getByLabel(/Fecha de inicio/)).toBeVisible();
  await expect(page.getByText(/se calcula automáticamente/)).toBeVisible();

  await page.getByRole("button", { name: "Crear tarea programada" }).click();
  await expect(page.getByText(/creada/)).toBeVisible();
  // The success banner also says "Nightly Factorial extract", and re-runs
  // against a long-lived isolated server can leave prior same-named rows
  // behind, so scope to the schedule row's name element and take the most
  // recently created match.
  await expect(page.locator("strong").filter({ hasText: "Nightly Factorial extract" }).last()).toBeVisible();
  // "Factorial · Extraer" also appears as a (non-visible) <option> in the
  // action <select> above the list, so scope to the schedule row's span.
  await expect(page.locator("span").filter({ hasText: "Factorial · Extraer" }).last()).toBeVisible();
});

test("run_workflow is selectable as a schedulable action and offers saved workflows", async ({ page }) => {
  await loginAsAdmin(page);

  // Seed one saved workflow so the picker has something to show.
  await page.goto("/flujos");
  await page.getByRole("button", { name: "Editor" }).click();
  await page.getByRole("button", { name: "Añadir bloque al flujo" }).click();
  await page.getByLabel("Nombre del flujo").fill("Flujo para programar");
  await page.getByRole("button", { name: "Guardar flujo" }).click();
  // Re-runs against a long-lived isolated server can leave prior
  // same-named workflows behind, so take the most recent match.
  await expect(page.getByText("Flujo para programar").last()).toBeVisible();

  await page.goto("/programacion");
  await page.getByLabel("Nombre de la tarea").fill("Flujo nocturno");
  await page.getByLabel("Acción a programar").selectOption("run_workflow");

  const workflowSelect = page.getByLabel("Flujo");
  await expect(workflowSelect).toBeVisible();
  // Options inside a closed native <select> report as "hidden" in Playwright
  // even though they're valid choices, so assert on the select's text content
  // rather than the option's visibility.
  await expect(workflowSelect).toContainText("Flujo para programar");

  await page.getByRole("button", { name: "Crear tarea programada" }).click();
  await expect(page.getByText(/creada/)).toBeVisible();
  await expect(page.locator("strong").filter({ hasText: "Flujo nocturno" }).last()).toBeVisible();
  // "Flujo (varios bloques)" also appears as a (non-visible) <option> in the
  // action <select> above the list, so scope to the schedule row's span.
  await expect(page.locator("span").filter({ hasText: "Flujo (varios bloques)" }).last()).toBeVisible();
});

test("scheduling a pipeline run requires choosing a configured pipeline", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/programacion");

  await page.getByLabel("Nombre de la tarea").fill("Pipeline nocturno");
  await page.getByLabel("Acción a programar").selectOption("run_pipeline");

  // Either a pipeline picker is shown (config.json has pipelines configured)
  // or an explicit "none configured" hint -- either way, `pipeline` must be
  // a real, deliberate field now, not silently absent. Selecting the action
  // triggers an async fetch, so wait for whichever of the two shows up
  // instead of checking isVisible() immediately (which would race the fetch).
  const pipelineSelect = page.getByLabel("Pipeline");
  const noPipelinesHint = page.getByText(/No hay pipelines configurados/);
  await expect(pipelineSelect.or(noPipelinesHint)).toBeVisible();
  const hasPicker = await pipelineSelect.isVisible();
  if (hasPicker) {
    await page.getByRole("button", { name: "Crear tarea programada" }).click();
    await expect(page.getByText(/creada/)).toBeVisible();
    await expect(page.locator("strong").filter({ hasText: "Pipeline nocturno" }).last()).toBeVisible();
  } else {
    await expect(page.getByText(/No hay pipelines configurados/)).toBeVisible();
  }
});
