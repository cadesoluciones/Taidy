import { expect, test } from "@playwright/test";

/**
 * Fase 6 gap closed: below the 860px breakpoint the sidebar used to just
 * `display: none` with no alternative way to navigate. Verifies the
 * hamburger-toggle drawer added to fix that actually works at a real
 * mobile viewport width, not just that the CSS rule exists.
 */
test.describe("Responsive navigation (narrow viewport)", () => {
  test.use({ viewport: { width: 390, height: 844 } }); // iPhone-class width

  test("sidebar is hidden until the menu toggle opens it, and a link reaches another page", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Usuario").fill("operator1");
    await page.getByLabel("Contraseña", { exact: true }).fill("OperatorPass2026!");
    await page.getByRole("button", { name: "Acceder al panel" }).click();
    await expect(page).toHaveURL("http://127.0.0.1:5173/");

    const nav = page.getByRole("navigation", { name: "Navegación principal" });
    await expect(nav).not.toBeInViewport();

    await page.getByRole("button", { name: "Abrir menú" }).click();
    await expect(nav).toBeInViewport();

    // "Actividad" starts collapsed (Home isn't one of its pages) -- expand
    // it before its "Historial" link becomes clickable.
    await nav.getByRole("button", { name: /Actividad/ }).click();
    await nav.getByRole("link", { name: "Historial" }).click();
    await expect(page).toHaveURL(/\/actividad\/historial$/);
    // Navigating closes the drawer automatically rather than leaving it
    // open over the new page.
    await expect(nav).not.toBeInViewport();
  });

  test("clicking the backdrop closes the drawer without navigating", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Usuario").fill("operator1");
    await page.getByLabel("Contraseña", { exact: true }).fill("OperatorPass2026!");
    await page.getByRole("button", { name: "Acceder al panel" }).click();
    await expect(page).toHaveURL("http://127.0.0.1:5173/");

    await page.getByRole("button", { name: "Abrir menú" }).click();
    const nav = page.getByRole("navigation", { name: "Navegación principal" });
    await expect(nav).toBeInViewport();

    // Click far enough right to land on the backdrop, not the drawer itself.
    await page.mouse.click(370, 400);
    await expect(nav).not.toBeInViewport();
    await expect(page).toHaveURL("http://127.0.0.1:5173/");
  });
});
