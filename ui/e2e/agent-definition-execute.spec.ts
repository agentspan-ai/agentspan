/**
 * E2E tests for the Execute button on the agent definition page.
 *
 * Verifies that clicking Execute navigates to the Run Agent page
 * with the agent name pre-selected.
 */
import { expect, Page, test } from "@playwright/test";

/**
 * Navigate to a real agent definition page.
 * Goes to the definitions list and clicks the first agent.
 */
async function goToFirstAgentDef(page: Page) {
  await page.goto("/agentDef");
  const firstAgentLink = page.locator("table a, [role='row'] a").first();
  await expect(firstAgentLink).toBeVisible({ timeout: 15000 });
  const agentName = await firstAgentLink.textContent();
  await firstAgentLink.click();
  await page.waitForURL(/\/agentDef\//, { timeout: 10000 });
  return agentName?.trim() || "";
}

test.describe("Agent definition — Execute button", () => {
  test("Execute button navigates to Run Agent page with agent pre-selected", async ({
    page,
  }) => {
    const agentName = await goToFirstAgentDef(page);

    // Click Execute button
    const executeBtn = page.locator("#head-action-run-btn");
    await expect(executeBtn).toBeVisible({ timeout: 10000 });
    await executeBtn.click();

    // Should navigate to the Run Agent page
    await page.waitForURL(/\/runAgent/, { timeout: 10000 });

    // The prompt field should be ready for input
    await expect(page.locator("#prompt-input")).toBeVisible({ timeout: 5000 });

    // The Run button should be visible
    await expect(page.locator("#run-workflow-btn")).toBeVisible();
  });

  test("no Save or Delete buttons on definition page", async ({ page }) => {
    await goToFirstAgentDef(page);

    // Should NOT have Save or Delete buttons
    await expect(
      page.locator("[data-testid='workflow-definition-save-button']"),
    ).not.toBeVisible();
    await expect(
      page.locator("[data-testid='workflow-definition-delete-button']"),
    ).not.toBeVisible();

    // SHOULD have Download and Execute
    await expect(page.locator("#head-action-download-btn")).toBeVisible();
    await expect(page.locator("#head-action-run-btn")).toBeVisible();
  });
});
