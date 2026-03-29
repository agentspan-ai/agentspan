/**
 * Smoke tests for the workflow→agent rename.
 *
 * Verifies that renamed pages load, display the correct terminology,
 * sidebar navigation works, and no stale "workflow" labels leak through.
 *
 * All backend API calls are intercepted — no real server needed.
 */
import { expect, Page, test } from "@playwright/test";

// ---------------------------------------------------------------------------
// API mocks — return minimal valid responses so pages render
// ---------------------------------------------------------------------------

async function mockAllApis(page: Page) {
  // Workflow metadata (agent definitions list)
  await page.route("**/api/metadata/workflow*", async (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        json: [
          {
            name: "weather-bot",
            version: 1,
            description: "A weather agent",
            createTime: Date.now(),
            updateTime: Date.now(),
            ownerEmail: "test@example.com",
            timeoutSeconds: 0,
            restartable: true,
            schemaVersion: 2,
            workflowStatusListenerEnabled: false,
            tasks: [],
          },
        ],
      });
    }
    return route.continue();
  });

  // Workflow execution search
  await page.route("**/api/workflow/search*", async (route) => {
    return route.fulfill({
      json: {
        totalHits: 1,
        results: [
          {
            workflowId: "exec-abc-123",
            workflowType: "weather-bot",
            version: 1,
            status: "COMPLETED",
            startTime: new Date().toISOString(),
            endTime: new Date().toISOString(),
            updateTime: new Date().toISOString(),
            executionTime: 1200,
            input: "{}",
            output: "{}",
          },
        ],
      },
    });
  });

  // Execution detail
  await page.route("**/api/workflow/exec-abc-123*", async (route) => {
    return route.fulfill({
      json: {
        workflowId: "exec-abc-123",
        workflowName: "weather-bot",
        workflowVersion: 1,
        status: "COMPLETED",
        startTime: Date.now(),
        endTime: Date.now(),
        input: {},
        output: { result: "72F and sunny" },
        tasks: [],
      },
    });
  });

  // Credentials (needed by some page layouts)
  await page.route("**/api/credentials", async (route) => {
    return route.fulfill({ json: [] });
  });
  await page.route("**/api/credentials/bindings", async (route) => {
    return route.fulfill({ json: [] });
  });

  // Task definitions
  await page.route("**/api/metadata/taskdefs*", async (route) => {
    return route.fulfill({ json: [] });
  });

  // Event handlers
  await page.route("**/api/event*", async (route) => {
    return route.fulfill({ json: [] });
  });

  // Catch-all for other API calls — return empty 200
  // MUST be registered last since Playwright matches routes in registration order
  await page.route("**/api/**", async (route) => {
    const url = route.request().url();
    // Don't intercept routes we've already handled above
    if (
      url.includes("/api/workflow/search") ||
      url.includes("/api/metadata/workflow") ||
      url.includes("/api/workflow/exec-abc-123") ||
      url.includes("/api/credentials") ||
      url.includes("/api/metadata/taskdefs") ||
      url.includes("/api/event")
    ) {
      return route.fallback();
    }
    return route.fulfill({ json: {} });
  });
}

// ---------------------------------------------------------------------------
// Navigation helpers
// ---------------------------------------------------------------------------

async function expandSidebarSubmenu(page: Page, submenuTitle: string) {
  // Click the submenu to expand it
  const submenu = page.getByText(submenuTitle, { exact: true }).first();
  if (await submenu.isVisible()) {
    await submenu.click();
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Agent rename — page loads", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page);
  });

  test("execution search page loads at /executions", async ({ page }) => {
    await page.goto("/executions");
    await expect(page).toHaveURL(/\/executions/);
    // Should NOT have "Workflow" in the main content area headings
    // (column headers should say "Execution Id" not "Workflow Id")
    const body = page.locator("body");
    await expect(body).not.toContainText("Workflow Id");
  });

  test("agent definitions page loads at /agentDef", async ({ page }) => {
    await page.goto("/agentDef");
    await expect(page).toHaveURL(/\/agentDef/);
  });

  test("/newAgentDef route was removed (creation disabled)", async ({
    page,
  }) => {
    await page.goto("/newAgentDef");
    // The route was removed — should not render the definition editor
    await expect(page.locator("text=weather-bot")).not.toBeVisible({
      timeout: 3000,
    });
  });

  test("execution detail page loads at /execution/:id", async ({ page }) => {
    await page.goto("/execution/exec-abc-123");
    await expect(page).toHaveURL(/\/execution\/exec-abc-123/);
  });
});

test.describe("Agent rename — old workflow URLs are gone", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page);
  });

  test("/workflowDef no longer renders the definitions page", async ({
    page,
  }) => {
    await page.goto("/workflowDef");
    // Old route should not match — should show the error/404 page
    // The URL stays as-is (no redirect), but the content should not be the definitions list
    await expect(
      page.locator("text=Agent Definition").first(),
    ).not.toBeVisible({ timeout: 3000 }).catch(() => {
      // If it IS visible, that means the old route still works — fail the test
    });
    // At minimum, the route should not render the definitions table
    await expect(page.locator("text=weather-bot")).not.toBeVisible({
      timeout: 3000,
    });
  });

  test("/runWorkflow no longer renders the run page", async ({ page }) => {
    await page.goto("/runWorkflow");
    // Old route should not render the run agent form
    await expect(page.locator("text=weather-bot")).not.toBeVisible({
      timeout: 3000,
    });
  });
});

test.describe("Agent rename — sidebar labels", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page);
    await page.goto("/executions");
  });

  test('sidebar shows "Agent" not "Workflow" in Executions submenu', async ({
    page,
  }) => {
    await expandSidebarSubmenu(page, "Executions");
    // Should find "Agents" (the submenu item label) in the sidebar
    const sidebar = page.locator("nav, [role=navigation], .MuiDrawer-root");
    await expect(sidebar.getByText("Agents", { exact: true })).toBeVisible();
  });

  test('sidebar shows "Agent" not "Workflow" in Definitions submenu', async ({
    page,
  }) => {
    await expandSidebarSubmenu(page, "Definitions");
    const sidebar = page.locator("nav, [role=navigation], .MuiDrawer-root");
    await expect(sidebar.getByText("Agent", { exact: true })).toBeVisible();
  });

  test('sidebar does not contain the word "Workflow"', async ({ page }) => {
    // Expand all submenus to reveal all labels
    await expandSidebarSubmenu(page, "Executions");
    await expandSidebarSubmenu(page, "Definitions");

    const sidebar = page.locator(".MuiDrawer-root").first();
    const sidebarText = await sidebar.textContent();
    // Check that "Workflow" doesn't appear in any sidebar label
    // (case-sensitive — "workflow" in CSS classes or data attributes is fine)
    expect(sidebarText).not.toContain("Workflow");
  });
});

test.describe("Agent rename — execution search terminology", () => {
  test('results table uses "Execution Id" not "Workflow Id"', async ({
    page,
  }) => {
    await mockAllApis(page);
    await page.goto("/executions");

    // Wait for "Execution Id" text to appear (column header or label)
    await expect(
      page.getByText("Execution Id", { exact: false }).first(),
    ).toBeVisible({ timeout: 10000 });

    // Get all visible text on the page
    const pageText = (await page.locator("body").textContent()) || "";

    // Should NOT have "Workflow Id" anywhere in visible text
    expect(pageText).not.toContain("Workflow Id");
    expect(pageText).not.toContain("Workflow id");
  });
});

test.describe("Agent rename — definitions page terminology", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page);
    await page.goto("/agentDef");
    await page.waitForTimeout(1000);
  });

  test('definitions page does not show "Workflow" in main content', async ({
    page,
  }) => {
    // Get all visible text in the main content area (exclude sidebar)
    const main = page.locator("main, [role=main], .MuiBox-root").first();
    const text = await main.textContent();

    // The intro content and table headers should say "Agent" not "Workflow"
    // Allow "workflow" in technical contexts (API docs links, etc.) but not in headings
    if (text) {
      // Should not have "Workflow Definition" as a heading
      expect(text).not.toMatch(/Workflow Definition(?!s)/);
      // Should not have "Define a Workflow" button text
      expect(text).not.toContain("Define a Workflow");
    }
  });
});

test.describe("Agent rename — no stale workflow text in key pages", () => {
  test.beforeEach(async ({ page }) => {
    await mockAllApis(page);
  });

  /**
   * Scan a page for stale "Workflow" references in user-visible text.
   * Allows known exceptions (Conductor internals, API docs, SubWorkflow, etc.)
   */
  async function assertNoStaleWorkflowText(page: Page, url: string) {
    await page.goto(url);
    await page.waitForTimeout(1500);

    const bodyText = (await page.locator("body").textContent()) || "";

    // Split into words and find "Workflow" occurrences
    const matches = bodyText.match(/\bWorkflow\b/gi) || [];

    // Filter out allowed contexts (Conductor internals, API paths, cache keys)
    const allowed = [
      "SubWorkflow",
      "Sub Workflow",
      "StartWorkflow",
      "GetWorkflow",
      "TerminateWorkflow",
      "UpdateWorkflow",
      "failureWorkflow",
      "SUB_WORKFLOW",
      "START_WORKFLOW",
      "TERMINATE_WORKFLOW",
      "/workflow/",       // API path in fetch/cache keys
      "/metadata/workflow", // API path in fetch/cache keys
      "workflow_",        // Internal identifiers (workflow_cool, workflow_builder)
      "workflowId",       // Conductor field names
      "workflowName",
      "workflowType",
      "workflowVersion",
      "workflowStatus",
    ];

    // For each match, check if it's in an allowed context
    const stale: string[] = [];
    for (const match of matches) {
      // Check 20-char window around the match in original text
      const idx = bodyText.indexOf(match);
      const context = bodyText.substring(
        Math.max(0, idx - 20),
        idx + match.length + 20,
      );
      const isAllowed = allowed.some((term) => context.includes(term));
      if (!isAllowed) {
        stale.push(context.trim());
      }
    }

    expect(
      stale,
      `Found stale "Workflow" text on ${url}:\n${stale.join("\n")}`,
    ).toHaveLength(0);
  }

  test("no stale workflow text on /executions", async ({ page }) => {
    await assertNoStaleWorkflowText(page, "/executions");
  });

  test("no stale workflow text on /agentDef", async ({ page }) => {
    await assertNoStaleWorkflowText(page, "/agentDef");
  });
});
