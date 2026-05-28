import { defineConfig, devices } from "@playwright/test";

const apiPort = 18180;
const uiPort = 15176;
const apiBaseUrl = `http://127.0.0.1:${apiPort}`;
const uiBaseUrl = `http://127.0.0.1:${uiPort}`;

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30000,
  use: {
    baseURL: uiBaseUrl,
    trace: "on-first-retry",
  },
  webServer: [
    {
      command:
        `powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:XIAGENT_DATABASE_PATH='.data/xiagent-e2e.sqlite3'; $env:XIAGENT_ASSET_STORAGE_DIR='.data/e2e-assets'; python -m uvicorn xiagent.api.app:app --host 127.0.0.1 --port ${apiPort}"`,
      cwd: "../..",
      url: `${apiBaseUrl}/api/health`,
    },
    {
      command:
        `powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:VITE_API_PROXY_TARGET='${apiBaseUrl}'; node ./node_modules/vite/bin/vite.js --host 127.0.0.1 --port ${uiPort}"`,
      url: uiBaseUrl,
    },
  ],
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
