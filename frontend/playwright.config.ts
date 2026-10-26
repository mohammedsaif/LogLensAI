import { defineConfig, devices } from "@playwright/test";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

// E2E runs the real backend (mock AI, throwaway SQLite DB) and the Vite dev server on dedicated ports.
const BACKEND_PORT = 8001;
const FRONTEND_PORT = 5174;
const backendDir = path.resolve(HERE, "../backend");
const python =
  process.env.BACKEND_PYTHON ??
  (process.platform === "win32" ? path.join(backendDir, ".venv", "Scripts", "python.exe") : path.join(backendDir, ".venv", "bin", "python"));
const dbFile = path.join(os.tmpdir(), `loglens-e2e-${process.pid}.db`).replace(/\\/g, "/");

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    acceptDownloads: true,
  },
  // PW_CHANNEL=msedge (or chrome) runs against an installed browser instead of the downloaded Chromium.
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], channel: process.env.PW_CHANNEL || undefined } }],
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:create_app --factory --port ${BACKEND_PORT}`,
      cwd: backendDir,
      url: `http://localhost:${BACKEND_PORT}/health/ready`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { DATABASE_URL: `sqlite:///${dbFile}`, AI_PROVIDER: "mock", LOG_LEVEL: "WARNING", RETENTION_DAYS: "0" },
    },
    {
      command: `npx vite --port ${FRONTEND_PORT} --strictPort`,
      url: `http://localhost:${FRONTEND_PORT}`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { VITE_PROXY_TARGET: `http://localhost:${BACKEND_PORT}` },
    },
  ],
});
