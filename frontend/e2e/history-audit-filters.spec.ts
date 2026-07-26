import { expect, test } from "@playwright/test";

test("History page's action filter actually narrows results, not just renders", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  // Generate at least one "Factorial · Subir" history entry to filter for.
  // Uses a Factorial action (not BC) because no other spec launches BC
  // concurrently -- other specs' BC actions (sync_bc, upload_bc) share a
  // conflict group in webapp/tasks.py's _CONFLICT_GROUPS and would race
  // this test under Playwright's parallel workers.
  await page.goto("/ejecutar/factorial-subir");
  await page.getByRole("button", { name: "Ejecutar subida Factorial" }).click();
  await expect(page.getByText(/Tarea iniciada/)).toBeVisible();

  await page.goto("/actividad/historial");
  await page.getByLabel("Acción").selectOption("upload_factorial");
  await expect(page.getByText(/Mostrando \d+ de \d+ ejecuciones/)).toBeVisible();
  await expect(page.getByText("upload_factorial").first()).toBeVisible();

  // A filter for an action that was never run this session must show none
  // -- proves the dropdown actually reaches the server-side filter instead
  // of just rendering unfiltered results underneath it.
  await page.getByLabel("Acción").selectOption("extract_bc");
  await expect(page.getByText("Ningún resultado con los filtros actuales.")).toBeVisible();
});

test("Audit page's event filter narrows to only login entries", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  await page.goto("/administracion/auditoria");
  await page.getByLabel("Evento").selectOption("login");
  await expect(page.getByText(/Mostrando \d+ de \d+ eventos/)).toBeVisible();
  const table = page.locator("table");
  await expect(table.getByRole("cell", { name: "Cierre de sesión" })).toHaveCount(0);
  await expect(table.getByRole("cell", { name: "Inicio de sesión" }).first()).toBeVisible();
});

test("a denied admin action shows up in the audit log as 'Acceso denegado'", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("operator1");
  await page.getByLabel("Contraseña", { exact: true }).fill("OperatorPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  // Operator has no UI path to an admin-only action, so trigger the 403
  // directly -- what matters here is that dependencies.require_role()
  // itself records the denial, not how the request was made.
  await page.request.post("http://127.0.0.1:8000/users", {
    data: { username: `denied_e2e_${Date.now()}`, password: "Xxxxxxxx1!", role: "App.Reader" },
  });

  await page.getByRole("button", { name: "Cerrar sesión" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  await page.goto("/administracion/auditoria");
  await page.getByLabel("Evento").selectOption("authorization");
  await expect(page.getByRole("cell", { name: "Acceso denegado" }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "operator1" }).first()).toBeVisible();
});
