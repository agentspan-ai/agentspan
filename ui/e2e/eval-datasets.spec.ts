/**
 * E2E tests for the Datasets split-panel page.
 *
 * All backend calls are intercepted — no real server needed.
 * No LLM assertions (per CLAUDE.md).
 */
import { expect, Page, test } from "@playwright/test";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const DATASETS_LIST = [
  {
    name: "billing-cases",
    updatedAt: "2026-05-20T08:00:00Z",
    cases: [
      {
        name: "refund_request",
        prompt: "I need a refund for order #123",
        assertions: ["handoff_to:billing", "output_contains:refund"],
        tags: ["billing"],
        semanticCriteria: "Response acknowledges refund intent",
      },
      {
        name: "account_query",
        prompt: "What is my account balance?",
        assertions: ["tool_used:lookup_account"],
        tags: [],
        semanticCriteria: null,
      },
    ],
  },
  {
    name: "tech-cases",
    updatedAt: "2026-05-19T07:00:00Z",
    cases: [
      {
        name: "crash_report",
        prompt: "My app crashes on startup",
        assertions: ["handoff_to:technical"],
        tags: ["tech"],
        semanticCriteria: null,
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function mockDatasetApis(page: Page) {
  // List all datasets
  await page.route("**/api/eval/datasets", async (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: DATASETS_LIST });
    }
    return route.continue();
  });

  // Dataset detail by name
  await page.route("**/api/eval/datasets/billing-cases", async (route) => {
    return route.fulfill({ json: DATASETS_LIST[0] });
  });

  await page.route("**/api/eval/datasets/tech-cases", async (route) => {
    return route.fulfill({ json: DATASETS_LIST[1] });
  });

  // Silence unrelated API calls
  await page.route("**/api/**", async (route) => {
    const url = route.request().url();
    if (url.includes("/api/eval/")) return route.fallback();
    return route.fulfill({ json: [] });
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Datasets split-panel", () => {
  test.beforeEach(async ({ page }) => {
    await mockDatasetApis(page);
    await page.goto("/experiments/datasets");
  });

  test("page title is 'Datasets'", async ({ page }) => {
    await expect(page).toHaveTitle("Datasets");
  });

  test("left panel lists both datasets", async ({ page }) => {
    await expect(page.getByText("billing-cases")).toBeVisible();
    await expect(page.getByText("tech-cases")).toBeVisible();
  });

  test("right panel shows placeholder when no dataset selected", async ({ page }) => {
    await expect(page.getByText("Select a dataset to view its cases")).toBeVisible();
  });

  test("clicking a dataset shows its cases on the right", async ({ page }) => {
    await page.getByText("billing-cases").click();
    // URL updates to include dataset name
    await expect(page).toHaveURL(/\/experiments\/datasets\/billing-cases/);
    // Right panel shows dataset name
    await expect(page.getByText("billing-cases").last()).toBeVisible();
    // Shows cases
    await expect(page.getByText("refund_request")).toBeVisible();
    await expect(page.getByText("account_query")).toBeVisible();
  });

  test("cases table shows Semantic Criterion column", async ({ page }) => {
    await page.goto("/experiments/datasets/billing-cases");
    await expect(page.getByText("Semantic Criterion")).toBeVisible();
    await expect(page.getByText("Response acknowledges refund intent")).toBeVisible();
  });

  test("cases table shows assertions as chips", async ({ page }) => {
    await page.goto("/experiments/datasets/billing-cases");
    await expect(page.getByText("handoff_to:billing")).toBeVisible();
    await expect(page.getByText("output_contains:refund")).toBeVisible();
  });

  test("navigating directly to dataset URL shows split panel with detail", async ({ page }) => {
    await page.goto("/experiments/datasets/tech-cases");
    // Left panel still shows both datasets
    await expect(page.getByText("billing-cases")).toBeVisible();
    await expect(page.getByText("tech-cases")).toBeVisible();
    // Right panel shows tech-cases detail
    await expect(page.getByText("crash_report")).toBeVisible();
  });

  test("empty state shows push_dataset SDK instruction", async ({ page }) => {
    // Mock empty list
    await page.route("**/api/eval/datasets", async (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({ json: [] });
      }
      return route.continue();
    });
    await page.reload();
    await expect(page.getByText(/runtime\.push_dataset/i)).toBeVisible();
  });
});
