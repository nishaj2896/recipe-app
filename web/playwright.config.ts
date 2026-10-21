import { randomBytes } from "node:crypto";

import { defineConfig } from "@playwright/test";

import { PHONE } from "./e2e/app";

// End-to-end tests drive the built app against the real API and Postgres
// (ADR-0006 rule 10). The database at DATABASE_URL must be migrated and
// synced first: `uv run alembic upgrade head && uv run recipe-app db sync`.
const CI = Boolean(process.env["CI"]);
const WEB_URL = "http://localhost:4173";
const API_URL = "http://localhost:8000";

// A throwaway cursor key, so a run needs no secrets.
const cursorKey = randomBytes(32).toString("base64url");

export default defineConfig({
  testDir: "e2e",
  forbidOnly: CI,
  retries: 0,
  // The motion budget measures timing, so tests don't compete for the CPU.
  workers: 1,
  reporter: CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: WEB_URL,
    ...PHONE,
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "uv run --frozen recipe-app",
      cwd: "..",
      url: `${API_URL}/api/v1/staples`,
      env: {
        CURSOR_ACTIVE_KID: "e2e",
        CURSOR_SIGNING_KEYS: JSON.stringify({ e2e: cursorKey }),
      },
      reuseExistingServer: !CI,
      stdout: "pipe",
    },
    {
      // The production build, so timings and markup are what users get.
      // `vite preview` proxies /api to the API like the dev server does.
      command: "npm run build && npx vite preview --port 4173 --strictPort",
      url: WEB_URL,
      env: { API_URL },
      reuseExistingServer: !CI,
      timeout: 120_000,
    },
  ],
});
