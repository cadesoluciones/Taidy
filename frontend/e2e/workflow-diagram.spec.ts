import { expect, test, type Page } from "@playwright/test";

async function loginAsAdmin(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");
}

/** Scoped to the designer's own diagram, not the whole page -- "Flujos
 * guardados" below renders one read-only diagram per saved workflow, so an
 * unscoped `.react-flow__edge` locator would also count edges belonging to
 * other, unrelated saved workflows. */
function designerDiagram(page: Page) {
  return page.getByTestId("designer-diagram");
}

async function connectByDrag(page: Page, sourceIndex: number, targetIndex: number) {
  const diagram = designerDiagram(page);
  const sourceHandle = diagram.locator(".react-flow__node").nth(sourceIndex).locator(".react-flow__handle-right");
  const targetHandle = diagram.locator(".react-flow__node").nth(targetIndex).locator(".react-flow__handle-left");
  const sourceBox = await sourceHandle.boundingBox();
  const targetBox = await targetHandle.boundingBox();
  if (!sourceBox || !targetBox) throw new Error("Handle bounding boxes not found");

  await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(targetBox.x + targetBox.width / 2, targetBox.y + targetBox.height / 2, { steps: 10 });
  await page.mouse.up();
}

test("interactive diagram: add two blocks, drag-connect them, and the dependency persists after save", async ({
  page,
}) => {
  await loginAsAdmin(page);
  await page.goto("/flujos");
  await page.getByRole("button", { name: "Editor" }).click();
  const diagram = designerDiagram(page);

  await page.getByRole("button", { name: "Añadir bloque al flujo" }).click();
  await expect(diagram.locator(".react-flow__node")).toHaveCount(1);
  await expect(page.getByLabel("Etiqueta del bloque seleccionado")).toHaveValue("Bloque 1");

  await page.getByRole("button", { name: "Añadir bloque al flujo" }).click();
  await expect(diagram.locator(".react-flow__node")).toHaveCount(2);
  await expect(page.getByLabel("Etiqueta del bloque seleccionado")).toHaveValue("Bloque 2");

  // No dependency yet -> the trigger-rule selector for the (currently
  // selected) second block must not be shown.
  await expect(page.getByLabel("¿Cuándo lanzar este bloque?")).toHaveCount(0);

  await connectByDrag(page, 0, 1);
  await expect(diagram.locator(".react-flow__edge")).toHaveCount(1);

  // Selecting "Bloque 2" (the dependency's target) now shows the trigger-rule
  // selector, proving the connection actually set depends_on, not just drew a line.
  await diagram.locator(".react-flow__node", { hasText: "Bloque 2" }).click();
  await expect(page.getByLabel("¿Cuándo lanzar este bloque?")).toBeVisible();

  const workflowName = `Flujo con dependencia E2E ${Date.now()}`;
  await page.getByLabel("Nombre del flujo").fill(workflowName);
  await page.getByRole("button", { name: "Guardar flujo" }).click();

  await expect(page.getByText(workflowName)).toBeVisible();
  const savedCard = page
    .locator("div")
    .filter({ hasText: workflowName })
    .filter({ has: page.getByRole("button", { name: "Editar flujo" }) })
    .last();

  // Reopen for edit -- the saved definition must still carry the dependency.
  await savedCard.getByRole("button", { name: "Editar flujo" }).click();
  await expect(diagram.locator(".react-flow__edge")).toHaveCount(1);
});

test("clicking an edge removes the dependency", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/flujos");
  await page.getByRole("button", { name: "Editor" }).click();
  const diagram = designerDiagram(page);

  await page.getByRole("button", { name: "Añadir bloque al flujo" }).click();
  await page.getByRole("button", { name: "Añadir bloque al flujo" }).click();
  await connectByDrag(page, 0, 1);
  await expect(diagram.locator(".react-flow__edge")).toHaveCount(1);

  // The interaction path is an intentionally invisible (stroke-opacity: 0),
  // wider hit-target for real pointer clicks. Playwright's element.click()
  // actionability checks (visibility, in-viewport) are unreliable against
  // this kind of zero-opacity SVG hit-target, so click via raw coordinates
  // instead -- the same approach connectByDrag() already uses successfully.
  const edgeBox = await diagram.locator(".react-flow__edge-interaction").boundingBox();
  if (!edgeBox) throw new Error("Edge bounding box not found");
  await page.mouse.click(edgeBox.x + edgeBox.width / 2, edgeBox.y + edgeBox.height / 2);
  await expect(diagram.locator(".react-flow__edge")).toHaveCount(0);
});

test("removing a block also drops it from other blocks' dependencies", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/flujos");
  await page.getByRole("button", { name: "Editor" }).click();
  const diagram = designerDiagram(page);

  await page.getByRole("button", { name: "Añadir bloque al flujo" }).click();
  await page.getByRole("button", { name: "Añadir bloque al flujo" }).click();
  await connectByDrag(page, 0, 1);
  await expect(diagram.locator(".react-flow__edge")).toHaveCount(1);

  // Select and remove "Bloque 1" (the dependency source) via the panel.
  await diagram.locator(".react-flow__node", { hasText: "Bloque 1" }).click();
  await page.getByRole("button", { name: "Quitar bloque" }).click();

  await expect(diagram.locator(".react-flow__node")).toHaveCount(1);
  await expect(diagram.locator(".react-flow__edge")).toHaveCount(0);
});
