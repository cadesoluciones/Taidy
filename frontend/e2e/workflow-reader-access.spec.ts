import { expect, test } from "@playwright/test";

test("admin can grant a Reader access to a specific workflow and it persists", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  // Seed a Reader-role user (default role for a freshly created account) to
  // grant access to -- unique name so repeat runs against the same
  // long-lived isolated server don't collide.
  const readerUsername = `rrhh_e2e_${Date.now()}`;
  await page.goto("/administracion/usuarios");
  await page.getByLabel("Nuevo usuario").click();
  const createForm = page.locator("form").filter({ has: page.getByRole("button", { name: "Crear usuario" }) });
  await createForm.getByLabel("Usuario", { exact: true }).fill(readerUsername);
  await createForm.getByLabel("Contraseña temporal (mín. 8 caracteres)").fill("Temporal2026!");
  await createForm.getByRole("button", { name: "Crear usuario" }).click();
  await expect(page.getByText(/creado/)).toBeVisible();

  // Create a workflow to restrict.
  await page.goto("/flujos");
  await page.getByRole("button", { name: "Editor" }).click();
  await page.getByRole("button", { name: "Añadir bloque al flujo" }).click();
  const workflowName = `Flujo RRHH E2E ${Date.now()}`;
  await page.getByLabel("Nombre del flujo").fill(workflowName);
  await page.getByRole("button", { name: "Guardar flujo" }).click();
  await expect(page.getByText(workflowName)).toBeVisible();

  const card = page.getByTestId("workflow-card").filter({ hasText: workflowName });
  await card.locator("select").filter({ has: page.locator(`option[value="${readerUsername}"]`) }).selectOption(readerUsername);

  const tag = card.locator("span", { hasText: readerUsername });
  await expect(tag).toBeVisible();

  // Reload to prove this was actually persisted server-side, not just local state.
  await page.reload();
  const cardAfterReload = page.getByTestId("workflow-card").filter({ hasText: workflowName });
  await expect(cardAfterReload.locator("span", { hasText: readerUsername })).toBeVisible();

  // Clean up.
  await cardAfterReload.getByRole("button", { name: "Borrar flujo" }).click();
  await page.getByRole("button", { name: "Borrar definitivamente" }).click();
  await expect(page.getByText(workflowName)).toHaveCount(0);
});

test("Reader can run a workflow they've been granted access to, but not one they haven't", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");

  const readerUsername = `compras_e2e_${Date.now()}`;
  await page.goto("/administracion/usuarios");
  await page.getByLabel("Nuevo usuario").click();
  const createForm = page.locator("form").filter({ has: page.getByRole("button", { name: "Crear usuario" }) });
  await createForm.getByLabel("Usuario", { exact: true }).fill(readerUsername);
  await createForm.getByLabel("Contraseña temporal (mín. 8 caracteres)").fill("Temporal2026!");
  await createForm.getByRole("button", { name: "Crear usuario" }).click();
  await expect(page.getByText(/creado/)).toBeVisible();

  await page.goto("/flujos");
  await page.getByRole("button", { name: "Editor" }).click();
  await page.getByRole("button", { name: "Añadir bloque al flujo" }).click();
  const workflowName = `Flujo Compras E2E ${Date.now()}`;
  await page.getByLabel("Nombre del flujo").fill(workflowName);
  await page.getByRole("button", { name: "Guardar flujo" }).click();
  await expect(page.getByText(workflowName)).toBeVisible();
  const card = page.getByTestId("workflow-card").filter({ hasText: workflowName });
  await card.locator("select").filter({ has: page.locator(`option[value="${readerUsername}"]`) }).selectOption(readerUsername);
  await expect(card.locator("span", { hasText: readerUsername })).toBeVisible();

  // The forced-password-change flow for a fresh account is exercised
  // elsewhere (login.spec.ts) -- here we only need the API-level access
  // rule, which doesn't depend on the frontend's Reader-facing UI (not
  // built yet; the assigned workflow isn't reachable from /flujos for a
  // Reader today, only via the future simplified Inicio). page.request
  // shares this browser context's cookie jar, so the session survives
  // across these direct API calls.
  await page.request.post("http://127.0.0.1:8000/auth/logout");
  const loginResp = await page.request.post("http://127.0.0.1:8000/auth/login", {
    data: { username: readerUsername, password: "Temporal2026!" },
  });
  expect(loginResp.status()).toBe(200);
  expect((await loginResp.json()).must_change_password).toBe(true);

  const changePwResp = await page.request.post("http://127.0.0.1:8000/auth/change-password", {
    data: { new_password: "ReaderE2EPass2026!", confirm_password: "ReaderE2EPass2026!" },
  });
  expect(changePwResp.status()).toBe(200);

  const workflowsResp = await page.request.get("http://127.0.0.1:8000/workflows");
  const { items } = await workflowsResp.json();
  const granted = items.find((w: { name: string }) => w.name === workflowName);
  expect(granted).toBeTruthy();

  const runResp = await page.request.post(`http://127.0.0.1:8000/workflows/${granted.id}/run`);
  expect(runResp.status()).toBe(200);

  // Clean up: log back in as admin to delete the workflow.
  await page.request.post("http://127.0.0.1:8000/auth/logout");
  await page.goto("/login");
  await page.getByLabel("Usuario").fill("admin");
  await page.getByLabel("Contraseña", { exact: true }).fill("E2ETestPass2026!");
  await page.getByRole("button", { name: "Acceder al panel" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5173/");
  await page.goto("/flujos");
  const cleanupCard = page.getByTestId("workflow-card").filter({ hasText: workflowName });
  await cleanupCard.getByRole("button", { name: "Borrar flujo" }).click();
  await page.getByRole("button", { name: "Borrar definitivamente" }).click();
});
