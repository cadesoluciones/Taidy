import { defineConfig } from "@playwright/test";

/**
 * Assumes the backend (api/) and frontend dev server are already running --
 * see README.md for how to start both. Deliberately not auto-starting the
 * API here: it needs isolated state (see api/tests/conftest.py's pattern),
 * which a Playwright webServer hook has no clean way to set up without
 * duplicating that isolation logic.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: {
    baseURL: process.env["E2E_BASE_URL"] ?? "http://127.0.0.1:5173",
  },
});
