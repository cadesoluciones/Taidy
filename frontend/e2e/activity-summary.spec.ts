import { expect, test } from "@playwright/test";

test("Inicio auto-generates the template activity summary without a manual click", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  // No button click: it must generate on its own once Inicio's dashboard
  // summary has loaded. Not launching a task to seed history here -- every
  // action is already used elsewhere as either a real launch or an
  // unused-control value for another spec's filter assertions (see
  // history-audit-filters.spec.ts) -- so assert on whichever of
  // build_template_summary()'s two well-defined phrases applies.
  await expect(page.getByText(/ejecuciones registradas|Todavía no se ha registrado ninguna ejecución/)).toBeVisible();

  // Manual "Actualizar" still works as an explicit refresh.
  await page.getByRole("button", { name: "Actualizar" }).click();
  await expect(page.getByText(/ejecuciones registradas|Todavía no se ha registrado ninguna ejecución/)).toBeVisible();
});

test("admin can switch the summary mode to IA in Configuración, and Inicio reflects the fallback when unconfigured", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  await page.goto("/administracion/configuracion");
  await expect(page.getByLabel("Plantilla (recomendado, sin coste)")).toBeChecked();
  // .click() + a separately-polled toBeChecked(), not .check(): the radio's
  // checked state only flips once the PATCH round-trip resolves and React
  // re-renders, and .check()'s own post-click verification doesn't wait for
  // that async state settling the way a plain expect(...).toBeChecked() does.
  await page.getByLabel("IA generativa").click();
  await expect(page.getByLabel("IA generativa")).toBeChecked();
  await expect(page.getByText("Guardado.")).toBeVisible();

  await page.goto("/");
  await page.getByRole("button", { name: "Actualizar" }).click();
  await expect(page.getByText(/no está disponible ahora mismo/)).toBeVisible();

  // Clean up so this doesn't leak into other specs sharing the same
  // long-lived isolated server.
  await page.goto("/administracion/configuracion");
  await page.getByLabel("Plantilla (recomendado, sin coste)").click();
  await expect(page.getByLabel("Plantilla (recomendado, sin coste)")).toBeChecked();
  await expect(page.getByText("Guardado.")).toBeVisible();
});
