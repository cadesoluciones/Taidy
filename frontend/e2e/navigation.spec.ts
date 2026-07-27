import { expect, test, type Page } from "@playwright/test";

/**
 * Broad sweep: every route the NavShell links to must render its expected
 * heading, with zero browser console errors, for both an Admin (sees all 13
 * pages) and a non-Admin (Administración redirects home). Requires the
 * isolated API + Vite dev servers already running (never the real
 * webapp/users.db).
 */

async function login(page: Page, username: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill(username);
  await page.getByLabel("Contraseña", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");
}

const ADMIN_ROUTES: Array<[string, string | RegExp]> = [
  ["/", /Bienvenido|NEXUS-BDB — Panel de datos/],
  ["/ejecutar/bc-extraer", "Extraer tablas de Business Central"],
  ["/ejecutar/bc-subir", "Subir CSVs de Business Central a Fabric OneLake"],
  ["/ejecutar/bc-sync", "Extraer + subir Business Central en un paso"],
  ["/ejecutar/factorial-extraer", "Extraer tablas de Factorial HR"],
  ["/ejecutar/factorial-subir", "Subir CSVs de Factorial a Fabric OneLake"],
  ["/ejecutar/factorial-sync", "Extraer + subir Factorial en un paso"],
  ["/ejecutar/pipelines", "Ejecutar un pipeline de Fabric Data Factory"],
  ["/flujos", "Flujos"],
  ["/programacion", "Tareas programadas"],
  ["/actividad/tareas-en-curso", "Tareas en curso"],
  ["/actividad/historial", "Historial de ejecuciones"],
  ["/administracion/usuarios", "Usuarios"],
  ["/administracion/auditoria", "Auditoría de seguridad"],
  ["/cuenta", "Mi cuenta"],
];

test.describe("Full navigation sweep (Admin)", () => {
  test("every page renders its heading with no console errors", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      // Chromium logs "Failed to load resource: ... 401" to the console for
      // ANY non-2xx network response -- a devtools artifact of the response
      // status, not a JS error. It can show up here from a polling hook's
      // in-flight request racing a navigation away from its page. Real
      // application errors (thrown exceptions) come through as `pageerror`
      // below, which this deliberately does NOT filter.
      if (msg.type() === "error" && !msg.text().startsWith("Failed to load resource")) {
        consoleErrors.push(msg.text());
      }
    });
    page.on("pageerror", (err) => consoleErrors.push(err.message));

    await login(page, "admin", "E2ETestPass2026!");

    for (const [path, heading] of ADMIN_ROUTES) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1, name: heading }).first()).toBeVisible();
    }

    expect(consoleErrors).toEqual([]);
  });
});

test.describe("Non-admin navigation", () => {
  test("Administración pages redirect a non-admin back to Inicio", async ({ page }) => {
    await login(page, "operator1", "OperatorPass2026!");

    await page.goto("/administracion/usuarios");
    await expect(page).toHaveURL("http://127.0.0.1:5173/");

    await page.goto("/administracion/auditoria");
    await expect(page).toHaveURL("http://127.0.0.1:5173/");
  });

  test("Administración section is not in the sidebar for a non-admin", async ({ page }) => {
    await login(page, "operator1", "OperatorPass2026!");
    await expect(page.getByRole("navigation").getByText("Administración")).toHaveCount(0);
  });

  test("Administración section IS in the sidebar for an admin", async ({ page }) => {
    await login(page, "admin", "E2ETestPass2026!");
    await expect(page.getByRole("navigation").getByText("Administración")).toBeVisible();
  });
});
