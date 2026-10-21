/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API runs on :8000 in development. Proxying /api keeps the app and the
// API on one origin, as in production, so the API needs no CORS (ADR-0006 rule 3).
const API_URL = process.env["API_URL"] ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": API_URL },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // tokens.test.ts reads the token file as text, so it must not be stubbed out.
    css: { include: [/tokens\.css/], modules: { classNameStrategy: "non-scoped" } },
  },
});
