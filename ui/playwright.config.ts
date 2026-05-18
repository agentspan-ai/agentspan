import { defineConfig, devices } from "@playwright/test";

const testHost = "127.0.0.1";
const testPort = 8082;

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./e2e-results",
  reporter: [["list"], ["html", { outputFolder: "e2e-report", open: "never" }]],
  use: {
    baseURL: `http://${testHost}:${testPort}`,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: `npx vite --host ${testHost} --port ${testPort}`,
    port: testPort,
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
