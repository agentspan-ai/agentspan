/**
 * E2E tests for the Add/Edit Credential dialog layout and alignment.
 * Runs against the live dev server on port 2345 (real backend on 8082).
 *
 * Validates:
 * - Quick-select LLM dropdown present and functional
 * - Name / Value fields have no overlapping labels or helper text
 * - Vertical spacing between fields is sufficient (no visual crowding)
 * - Screenshots captured for manual review
 */
import { expect, Page, test } from "@playwright/test";

const BASE = "http://localhost:2345";

async function openAddDialog(page: Page) {
  await page.goto(`${BASE}/credentials`);
  await page.waitForLoadState("networkidle");
  // Use the header button specifically (there's also one in the empty-state NoDataComponent)
  await page.locator("#section-header-container").getByRole("button", { name: /Add Credential/i }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
}

test.describe("Add Credential dialog — layout & alignment", () => {
  test("dialog opens and shows quick-select dropdown", async ({ page }) => {
    await openAddDialog(page);
    const dropdown = page.getByRole("combobox", { name: /Quick select/i });
    await expect(dropdown).toBeVisible();
    await page.screenshot({
      path: "e2e-results/dialog-initial.png",
      fullPage: false,
    });
  });

  test("Name field label does not overlap helper text", async ({ page }) => {
    await openAddDialog(page);

    const nameInput = page.getByLabel("Name");
    const helperText = page.getByText(/UPPER_SNAKE_CASE/i);

    await expect(nameInput).toBeVisible();
    await expect(helperText).toBeVisible();

    const inputBox = await nameInput.boundingBox();
    const helperBox = await helperText.boundingBox();

    expect(inputBox).not.toBeNull();
    expect(helperBox).not.toBeNull();

    // Helper text must be BELOW the input field (not overlapping)
    const inputBottom = inputBox!.y + inputBox!.height;
    expect(helperBox!.y).toBeGreaterThan(inputBottom - 4); // 4px tolerance

    console.log(`Name input bottom: ${inputBottom.toFixed(0)}px`);
    console.log(`Helper text top:   ${helperBox!.y.toFixed(0)}px`);
    console.log(`Gap: ${(helperBox!.y - inputBottom).toFixed(0)}px`);
  });

  test("Value field label does not overlap Name helper text", async ({ page }) => {
    await openAddDialog(page);

    const helperText = page.getByText(/UPPER_SNAKE_CASE/i);
    const valueInput = page.getByRole("textbox", { name: "Value" });

    await expect(helperText).toBeVisible();
    await expect(valueInput).toBeVisible();

    const helperBox = await helperText.boundingBox();
    const valueBox = await valueInput.boundingBox();

    expect(helperBox).not.toBeNull();
    expect(valueBox).not.toBeNull();

    const helperBottom = helperBox!.y + helperBox!.height;

    // Value input must start well below the Name helper text
    expect(valueBox!.y).toBeGreaterThan(helperBottom + 8);

    console.log(`Name helper bottom: ${helperBottom.toFixed(0)}px`);
    console.log(`Value input top:    ${valueBox!.y.toFixed(0)}px`);
    console.log(`Gap: ${(valueBox!.y - helperBottom).toFixed(0)}px`);
  });

  test("Value helper text does not overlap Value input", async ({ page }) => {
    await openAddDialog(page);

    const valueInput = page.getByRole("textbox", { name: "Value" });
    const valueHelper = page.getByRole("dialog").locator("p.MuiFormHelperText-root", { hasText: /Encrypted at rest/i });

    await expect(valueInput).toBeVisible();
    await expect(valueHelper).toBeVisible();

    const inputBox = await valueInput.boundingBox();
    const helperBox = await valueHelper.boundingBox();

    const inputBottom = inputBox!.y + inputBox!.height;
    expect(helperBox!.y).toBeGreaterThan(inputBottom - 4);

    console.log(`Value input bottom:  ${inputBottom.toFixed(0)}px`);
    console.log(`Value helper top:    ${helperBox!.y.toFixed(0)}px`);
  });

  test("quick-select auto-fills Name field on selection", async ({ page }) => {
    await openAddDialog(page);

    // Open the autocomplete
    await page.getByRole("combobox", { name: /Quick select/i }).click();

    // Type to filter
    await page.keyboard.type("Anthropic");
    await expect(page.getByRole("option", { name: /ANTHROPIC_API_KEY/i })).toBeVisible();
    await page.getByRole("option", { name: /ANTHROPIC_API_KEY/i }).click();

    // Name field should now have the selected value
    const nameInput = page.getByLabel("Name");
    await expect(nameInput).toHaveValue("ANTHROPIC_API_KEY");

    await page.screenshot({
      path: "e2e-results/dialog-after-quickselect.png",
      fullPage: false,
    });
  });

  test("quick-select shows provider subtitle in options", async ({ page }) => {
    await openAddDialog(page);

    await page.getByRole("combobox", { name: /Quick select/i }).click();
    await page.keyboard.type("OpenAI");

    // Should see both the key name and the provider
    await expect(page.getByRole("option", { name: /^OPENAI_API_KEY/ })).toBeVisible();
    await expect(page.getByText("OpenAI (GPT-4, GPT-4o, etc.)")).toBeVisible();

    await page.screenshot({
      path: "e2e-results/dialog-quickselect-dropdown.png",
      fullPage: false,
    });
  });

  test("all LLM providers are present in quick-select", async ({ page }) => {
    await openAddDialog(page);
    await page.getByRole("combobox", { name: /Quick select/i }).click();

    // Type nothing to see all options — MUI Autocomplete shows options on click
    const expectedKeys = [
      "ANTHROPIC_API_KEY",
      "OPENAI_API_KEY",
      "GEMINI_API_KEY",
      "MISTRAL_API_KEY",
      "GROQ_API_KEY",
    ];

    for (const key of expectedKeys) {
      await page.getByRole("combobox", { name: /Quick select/i }).clear();
      await page.keyboard.type(key.split("_")[0]); // type first word
      await expect(page.getByRole("option", { name: new RegExp(`^${key}`, "i") })).toBeVisible();
    }
  });

  test("divider separates quick-select from Name/Value fields", async ({ page }) => {
    await openAddDialog(page);

    // MUI Divider renders as <hr>
    const divider = page.locator("hr");
    await expect(divider).toBeVisible();

    const dropdownBox = await page.getByRole("combobox", { name: /Quick select/i }).boundingBox();
    const dividerBox = await divider.boundingBox();
    const nameBox = await page.getByLabel("Name").boundingBox();

    // Order should be: dropdown → divider → name field
    expect(dividerBox!.y).toBeGreaterThan(dropdownBox!.y + dropdownBox!.height - 4);
    expect(nameBox!.y).toBeGreaterThan(dividerBox!.y + dividerBox!.height - 4);

    console.log(`Dropdown bottom: ${(dropdownBox!.y + dropdownBox!.height).toFixed(0)}px`);
    console.log(`Divider top:     ${dividerBox!.y.toFixed(0)}px`);
    console.log(`Name top:        ${nameBox!.y.toFixed(0)}px`);
  });

  test("screenshot of full dialog for visual review", async ({ page }) => {
    await openAddDialog(page);

    // Clip to just the dialog
    const dialog = page.getByRole("dialog");
    const dialogBox = await dialog.boundingBox();

    await page.screenshot({
      path: "e2e-results/dialog-full.png",
      clip: dialogBox ?? undefined,
    });

    // Just assert dialog is visible — screenshot is the review artifact
    await expect(dialog).toBeVisible();
  });

  test("edit mode has no quick-select dropdown", async ({ page }) => {
    await page.goto(`${BASE}/credentials`);
    await page.waitForLoadState("networkidle");

    // Need at least one credential to edit — check if there are any
    const editButtons = page.locator('[data-testid^="edit-"]');
    const count = await editButtons.count();

    if (count === 0) {
      test.skip(true, "No credentials to edit — create one first");
      return;
    }

    await editButtons.first().click();
    await expect(page.getByRole("dialog")).toBeVisible();

    // Quick-select should NOT be present in edit mode
    await expect(page.getByLabel(/Quick select/i)).not.toBeVisible();

    await page.screenshot({
      path: "e2e-results/dialog-edit-mode.png",
      fullPage: false,
    });
  });
});
