/**
 * E2E tests for Eval Runs list and detail pages.
 *
 * All backend calls are intercepted — no real server needed.
 * No LLM assertions (per CLAUDE.md).
 */
import { expect, Page, test } from "@playwright/test";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const EVAL_RUNS_PAGE: Record<string, any> = {
  totalHits: 3,
  results: [
    {
      id: "run-aaa-111",
      name: "eval_handoff_v2",
      agentName: "support-agent",
      timestamp: "2026-05-20T10:00:00Z",
      totalCases: 4,
      passedCases: 4,
      strategy: "handoff",
    },
    {
      id: "run-bbb-222",
      name: "billing_routing",
      agentName: "billing-agent",
      timestamp: "2026-05-19T09:00:00Z",
      totalCases: 5,
      passedCases: 3,
    },
    {
      id: "run-ccc-333",
      agentName: "tech-agent",
      timestamp: "2026-05-18T08:00:00Z",
      totalCases: 2,
      passedCases: 0,
    },
  ],
};

const EVAL_RUN_DETAIL: Record<string, any> = {
  id: "run-aaa-111",
  name: "eval_handoff_v2",
  agentName: "support-agent",
  timestamp: "2026-05-20T10:00:00Z",
  totalCases: 2,
  passedCases: 1,
  strategy: "handoff",
  ranBy: "test_script.py",
  cases: [
    {
      id: "case-1",
      name: "routes_billing_correctly",
      passed: true,
      prompt: "I need a refund for order #123",
      output: "Routing to billing department.",
      agentName: "support-agent",
      checks: [
        { id: "chk-1", check: "status", passed: true, message: "" },
        { id: "chk-2", check: "handoff_to:billing", passed: true, message: "" },
      ],
    },
    {
      id: "case-2",
      name: "routes_tech_correctly",
      passed: false,
      prompt: "My app crashes on startup",
      output: "Sorry I cannot help.",
      agentName: "support-agent",
      checks: [
        { id: "chk-3", check: "status", passed: true, message: "" },
        {
          id: "chk-4",
          check: "handoff_to:technical",
          passed: false,
          message: "Expected handoff to 'technical', but none occurred.",
        },
        {
          id: "chk-5",
          check: "strategy_validation",
          passed: true,
          message: "",
          score: 0.87,
          reasoning: "The agent followed the handoff strategy correctly.",
        },
      ],
    },
  ],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function mockEvalApis(page: Page) {
  await page.route("**/api/eval/runs?*", async (route) => {
    return route.fulfill({ json: EVAL_RUNS_PAGE });
  });

  await page.route("**/api/eval/runs/run-aaa-111", async (route) => {
    return route.fulfill({ json: EVAL_RUN_DETAIL });
  });

  // Silence unrelated API calls
  await page.route("**/api/**", async (route) => {
    const url = route.request().url();
    if (url.includes("/api/eval/")) return route.fallback();
    return route.fulfill({ json: [] });
  });
}

// ---------------------------------------------------------------------------
// Eval Runs List tests
// ---------------------------------------------------------------------------

test.describe("Eval Runs list", () => {
  test.beforeEach(async ({ page }) => {
    await mockEvalApis(page);
    await page.goto("/experiments/eval-runs");
  });

  test("page title is 'Eval Runs'", async ({ page }) => {
    await expect(page).toHaveTitle("Eval Runs");
  });

  test("stats row shows correct totals", async ({ page }) => {
    await expect(page.getByText("TOTAL RUNS")).toBeVisible();
    await expect(page.getByText("3")).toBeVisible();
    // 1 run is all-passing (run-aaa-111: 4/4)
    await expect(page.getByText("PASSING")).toBeVisible();
    await expect(page.getByText("FAILING")).toBeVisible();
  });

  test("table shows run names and agent chips", async ({ page }) => {
    await expect(page.getByText("eval_handoff_v2")).toBeVisible();
    await expect(page.getByText("billing_routing")).toBeVisible();
    // Third run has no name — should show truncated UUID
    await expect(page.getByText("run-ccc-")).toBeVisible();
  });

  test("table shows agent name chips", async ({ page }) => {
    await expect(page.getByText("support-agent")).toBeVisible();
    await expect(page.getByText("billing-agent")).toBeVisible();
    await expect(page.getByText("tech-agent")).toBeVisible();
  });

  test("cases column shows pass/fail badges", async ({ page }) => {
    // billing_routing has 3 pass and 2 fail
    await expect(page.getByText("3 pass")).toBeVisible();
    await expect(page.getByText("2 fail")).toBeVisible();
  });

  test("search filters rows by run name", async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search by run name/i);
    await searchInput.fill("billing");
    await expect(page.getByText("billing_routing")).toBeVisible();
    await expect(page.getByText("eval_handoff_v2")).not.toBeVisible();
  });

  test("agent filter dropdown filters by agent", async ({ page }) => {
    // Click the agent filter Select
    await page.getByRole("combobox").first().click();
    await page.getByRole("option", { name: "support-agent" }).click();
    await expect(page.getByText("eval_handoff_v2")).toBeVisible();
    await expect(page.getByText("billing_routing")).not.toBeVisible();
  });

  test("clicking a row navigates to detail page", async ({ page }) => {
    await page.getByText("eval_handoff_v2").click();
    await expect(page).toHaveURL(/\/experiments\/eval-runs\/run-aaa-111/);
  });
});

// ---------------------------------------------------------------------------
// Eval Run Detail tests
// ---------------------------------------------------------------------------

test.describe("Eval Run Detail", () => {
  test.beforeEach(async ({ page }) => {
    await mockEvalApis(page);
    await page.goto("/experiments/eval-runs/run-aaa-111");
  });

  test("page title uses run name", async ({ page }) => {
    await expect(page).toHaveTitle("eval_handoff_v2");
  });

  test("section header shows run name", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "eval_handoff_v2" })).toBeVisible();
  });

  test("metadata card shows agent, strategy, ran by", async ({ page }) => {
    await expect(page.getByText("support-agent")).toBeVisible();
    await expect(page.getByText("handoff")).toBeVisible();
    await expect(page.getByText("test_script.py")).toBeVisible();
  });

  test("metadata card shows pass rate bar", async ({ page }) => {
    await expect(page.getByText("50%")).toBeVisible();
  });

  test("case list shows both cases", async ({ page }) => {
    await expect(page.getByText("routes_billing_correctly")).toBeVisible();
    await expect(page.getByText("routes_tech_correctly")).toBeVisible();
  });

  test("case header shows prompt text under case name", async ({ page }) => {
    await expect(page.getByText("I need a refund for order #123")).toBeVisible();
    await expect(page.getByText("My app crashes on startup")).toBeVisible();
  });

  test("expanding a passing case shows checks", async ({ page }) => {
    // Click to expand the first case accordion
    await page.getByText("routes_billing_correctly").click();
    await expect(page.getByText("handoff_to:billing")).toBeVisible();
  });

  test("expanding a failing case shows failed check with message", async ({ page }) => {
    await page.getByText("routes_tech_correctly").click();
    await expect(page.getByText(/Expected handoff to 'technical'/i)).toBeVisible();
  });

  test("expanding a case shows agent output box", async ({ page }) => {
    await page.getByText("routes_billing_correctly").click();
    await expect(page.getByText("AGENT OUTPUT")).toBeVisible();
    await expect(page.getByText("Routing to billing department.")).toBeVisible();
  });

  test("semantic check shows score and reasoning in purple box", async ({ page }) => {
    await page.getByText("routes_tech_correctly").click();
    // Score from fixture is 0.87
    await expect(page.getByText("0.87")).toBeVisible();
    await expect(page.getByText("The agent followed the handoff strategy correctly.")).toBeVisible();
  });
});
