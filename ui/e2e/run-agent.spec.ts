/**
 * E2E tests for the Run Agent page.
 *
 * Verifies the simplified agent run flow: select agent, enter prompt, submit.
 * All backend API calls are intercepted — no real server needed.
 */
import { expect, Page, test } from "@playwright/test";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const AGENT_DEF = {
  name: "weather-bot",
  version: 1,
  description: "A weather agent",
  ownerEmail: "test@example.com",
  timeoutSeconds: 0,
  restartable: true,
  schemaVersion: 2,
  workflowStatusListenerEnabled: false,
  tasks: [],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function mockApis(page: Page) {
  // Agent definitions list (for dropdown)
  await page.route("**/api/metadata/workflow?short=true*", async (route) => {
    return route.fulfill({ json: [AGENT_DEF] });
  });

  // Fetch specific agent definition
  await page.route("**/api/metadata/workflow/weather-bot*", async (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: AGENT_DEF });
    }
    return route.continue();
  });

  // Start agent endpoint
  await page.route("**/api/agent/start", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      // Validate the payload has the correct structure
      if (!body.agentConfig || !body.prompt) {
        return route.fulfill({
          status: 400,
          json: { message: "Missing agentConfig or prompt" },
        });
      }
      return route.fulfill({
        contentType: "text/plain",
        body: "exec-new-123-456",
      });
    }
    return route.continue();
  });

  // Catch-all for other API calls
  await page.route("**/api/**", async (route) => {
    const url = route.request().url();
    if (
      url.includes("/api/metadata/workflow") ||
      url.includes("/api/agent/start")
    ) {
      return route.fallback();
    }
    return route.fulfill({ json: {} });
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Run Agent page", () => {
  test.beforeEach(async ({ page }) => {
    await mockApis(page);
  });

  test("page loads with correct title and form elements", async ({ page }) => {
    await page.goto("/runAgent");

    // Title
    await expect(page).toHaveTitle("Run Agent");

    // Agent name dropdown
    await expect(page.locator("#workflow-name-dropdown")).toBeVisible();

    // Prompt text area
    await expect(page.locator("#prompt-input")).toBeVisible();

    // Run button
    await expect(page.locator("#run-workflow-btn")).toBeVisible();
    await expect(page.locator("#run-workflow-btn")).toContainText("Run agent");
  });

  test("shows validation error when no agent selected", async ({ page }) => {
    await page.goto("/runAgent");
    await page.locator("#prompt-input").fill("What is the weather?");

    // Click run without selecting an agent
    await page.locator("#run-workflow-btn").click();

    // Should show error
    await expect(page.getByText("Please select an agent")).toBeVisible();
  });

  test("shows validation error when no prompt entered", async ({ page }) => {
    await page.goto("/runAgent");

    // Type agent name and select first matching option
    const input = page.locator("#workflow-name-dropdown");
    await input.click();
    await input.fill("weather");
    // Select the first option in the dropdown
    await page.getByRole("option").first().click();

    // Click run without entering a prompt
    await page.locator("#run-workflow-btn").click();

    // Should show error
    await expect(page.getByText("Please enter a prompt")).toBeVisible();
  });

  test("sends correct wire format to /api/agent/start", async ({ page }) => {
    let capturedPayload: any = null;

    // Intercept the start endpoint to capture and validate the payload
    await page.route("**/api/agent/start", async (route) => {
      capturedPayload = route.request().postDataJSON();
      return route.fulfill({
        contentType: "text/plain",
        body: "exec-wire-test-123",
      });
    });

    await page.goto("/runAgent");

    // Type agent name and select first matching option
    const input = page.locator("#workflow-name-dropdown");
    await input.click();
    await input.fill("weather");
    await page.getByRole("option").first().click();

    // Enter prompt
    await page.locator("#prompt-input").fill("Tell me about NYC weather");

    // Submit
    await page.locator("#run-workflow-btn").click();

    // Wait for success
    await expect(page.getByText("Agent started")).toBeVisible({
      timeout: 15000,
    });

    // Validate the wire format matches StartRequest.java
    expect(capturedPayload).not.toBeNull();
    expect(capturedPayload.agentConfig).toBeDefined();
    expect(capturedPayload.prompt).toBe("Tell me about NYC weather");

    // Should NOT have legacy Conductor fields
    expect(capturedPayload.correlationId).toBeUndefined();
    expect(capturedPayload.taskToDomain).toBeUndefined();
    expect(capturedPayload.idempotencyKey).toBeUndefined();
    expect(capturedPayload.version).toBeUndefined();
  });

  test("shows error when agent start fails", async ({ page }) => {
    // Intercept start route to return error
    await page.route("**/api/agent/start", async (route) => {
      return route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          message: "Internal server error: model not configured",
        }),
      });
    });

    await page.goto("/runAgent");

    // Type agent name and select first matching option
    const input = page.locator("#workflow-name-dropdown");
    await input.click();
    await input.fill("weather");
    await page.getByRole("option").first().click();
    await page.locator("#prompt-input").fill("Hello");

    // Submit
    await page.locator("#run-workflow-btn").click();

    // Should show error
    await expect(page.getByText(/error/i)).toBeVisible({ timeout: 15000 });
  });

  test("reset button clears the form", async ({ page }) => {
    await page.goto("/runAgent");

    // Type agent name and select first matching option
    const input = page.locator("#workflow-name-dropdown");
    await input.click();
    await input.fill("weather");
    await page.getByRole("option").first().click();
    await page.locator("#prompt-input").fill("Some prompt");

    // Click reset
    await page.locator("#clear-info-btn").click();

    // Prompt should be empty
    await expect(page.locator("#prompt-input")).toHaveValue("");
  });

  test("form has prompt field and advanced options accordion", async ({
    page,
  }) => {
    await page.goto("/runAgent");

    const body = page.locator("body");

    // Should NOT have legacy fields visible by default
    await expect(body).not.toContainText("Correlation id");
    await expect(body).not.toContainText("Tasks to domain");
    await expect(body).not.toContainText("Input params");

    // SHOULD have the prompt field
    await expect(body).toContainText("Prompt");

    // Advanced options accordion should exist
    await expect(page.getByText("Advanced options")).toBeVisible();

    // Expand it
    await page.getByText("Advanced options").click();

    // Should now show optional fields
    await expect(page.locator("#model-input")).toBeVisible();
    await expect(page.locator("#timeout-input")).toBeVisible();
    await expect(page.locator("#idempotency-input")).toBeVisible();
    await expect(page.locator("#media-input")).toBeVisible();
  });
});
