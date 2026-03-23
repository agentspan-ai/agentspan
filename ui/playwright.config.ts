import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./e2e-results",
  reporter: [["list"], ["html", { outputFolder: "e2e-report", open: "never" }]],
  use: {
    baseURL: "http://localhost:8082",
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
    command: "npx vite --port 8082",
    port: 8082,
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
