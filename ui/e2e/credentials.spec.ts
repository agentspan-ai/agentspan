/**
 * E2E tests for the Credentials management page.
 *
 * All backend API calls are intercepted with page.route() so no real server is needed.
 */
import { expect, Page, test } from "@playwright/test";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const CREDENTIALS = [
  { name: "GITHUB_TOKEN", partial: "ghp_...6789", updated_at: "2026-03-20T12:00:00Z" },
  { name: "OPENAI_KEY", partial: "sk-...abcd", updated_at: "2026-03-19T08:30:00Z" },
];

const BINDINGS = [
  { logical_key: "GH_TOKEN", store_name: "GITHUB_TOKEN" },
  { logical_key: "GITHUB", store_name: "GITHUB_TOKEN" },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function mockCredentialApis(page: Page, opts: { status401?: boolean } = {}) {
  const { status401 = false } = opts;

  // Credentials list
  await page.route("**/api/credentials", async (route) => {
    if (route.request().method() === "GET") {
      if (status401) {
        return route.fulfill({ status: 401, body: JSON.stringify({ message: "Unauthorized" }) });
      }
      return route.fulfill({ json: CREDENTIALS });
    }
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      return route.fulfill({ json: { name: body.name, partial: "***...", updated_at: new Date().toISOString() } });
    }
    return route.continue();
  });

  // Single credential update
  await page.route("**/api/credentials/**", async (route) => {
    const method = route.request().method();
    if (method === "PUT") {
      return route.fulfill({ json: {} });
    }
    if (method === "DELETE") {
      return route.fulfill({ status: 204, body: "" });
    }
    return route.continue();
  });

  // Bindings list
  await page.route("**/api/credentials/bindings", async (route) => {
    if (route.request().method() === "GET") {
      if (status401) {
        return route.fulfill({ status: 401, body: JSON.stringify({ message: "Unauthorized" }) });
      }
      return route.fulfill({ json: BINDINGS });
    }
    return route.continue();
  });

  // Single binding upsert / delete
  await page.route("**/api/credentials/bindings/**", async (route) => {
    const method = route.request().method();
    if (method === "PUT") {
      return route.fulfill({ json: {} });
    }
    if (method === "DELETE") {
      return route.fulfill({ status: 204, body: "" });
    }
    return route.continue();
  });
}

async function goToCredentials(page: Page) {
  await page.goto("/credentials");
  await page.waitForLoadState("networkidle");
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Credentials page", () => {
  test("renders credential list with name and partial value", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);

    await expect(page.getByText("GITHUB_TOKEN")).toBeVisible();
    await expect(page.getByText("ghp_...6789")).toBeVisible();
    await expect(page.getByText("OPENAI_KEY")).toBeVisible();
    await expect(page.getByText("sk-...abcd")).toBeVisible();
  });

  test("page title is Credentials", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);
    await expect(page).toHaveTitle(/Credentials/);
  });

  test("Settings > Credentials appears in the sidebar", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);
    // The sidebar Settings menu item should be present
    await expect(page.getByText("Settings")).toBeVisible();
  });

  test("search filters credentials by name", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);

    const searchBox = page.getByPlaceholder("Search credentials…");
    await searchBox.fill("GITHUB");

    await expect(page.getByText("GITHUB_TOKEN")).toBeVisible();
    await expect(page.getByText("OPENAI_KEY")).not.toBeVisible();
  });

  test("clearing search restores all credentials", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);

    const searchBox = page.getByPlaceholder("Search credentials…");
    await searchBox.fill("GITHUB");
    await searchBox.clear();

    await expect(page.getByText("GITHUB_TOKEN")).toBeVisible();
    await expect(page.getByText("OPENAI_KEY")).toBeVisible();
  });

  test("no-match search shows empty state message", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);

    await page.getByPlaceholder("Search credentials…").fill("ZZZNOMATCH");
    await expect(page.getByText(/No credentials match/)).toBeVisible();
  });

  test("expands binding row and shows binding chips", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);

    await page.getByTestId("expand-GITHUB_TOKEN").click();

    // Chip label is "GH_TOKEN → GITHUB_TOKEN" — use regex for substring match
    await expect(page.getByText(/GH_TOKEN → GITHUB_TOKEN/)).toBeVisible();
    await expect(page.getByText(/GITHUB → GITHUB_TOKEN/)).toBeVisible();
  });

  test("collapsing binding row hides chips", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);

    await page.getByTestId("expand-GITHUB_TOKEN").click();
    await expect(page.getByText(/GH_TOKEN → GITHUB_TOKEN/)).toBeVisible();

    await page.getByTestId("expand-GITHUB_TOKEN").click();
    await expect(page.getByText(/GH_TOKEN → GITHUB_TOKEN/)).not.toBeVisible();
  });

  test("expanded row shows empty state when no bindings", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);

    // OPENAI_KEY has no bindings in our fixture
    await page.getByTestId("expand-OPENAI_KEY").click();
    await expect(page.getByText(/No bindings/)).toBeVisible();
  });

  test("delete opens confirm dialog requiring name entry", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);

    await page.getByTestId("delete-GITHUB_TOKEN").click();

    // ConfirmChoiceDialog should appear — wait for dialog role first
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByRole("dialog").getByText("Delete Credential")).toBeVisible();
  });

  test("delete confirm button is disabled until correct name is typed", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);

    await page.getByTestId("delete-GITHUB_TOKEN").click();

    // Find the confirm button — look for role=button with text "Confirm" or "Delete"
    const confirmBtn = page.getByRole("button", { name: /confirm/i });
    await expect(confirmBtn).toBeDisabled();

    // Type partial name — still disabled
    await page.getByRole("textbox").fill("GITHUB");
    await expect(confirmBtn).toBeDisabled();

    // Type full name — now enabled
    await page.getByRole("textbox").fill("GITHUB_TOKEN");
    await expect(confirmBtn).toBeEnabled();
  });

  test("confirms delete and shows success toast", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);

    await page.getByTestId("delete-GITHUB_TOKEN").click();
    await page.getByRole("textbox").fill("GITHUB_TOKEN");
    await page.getByRole("button", { name: /confirm/i }).click();

    await expect(page.getByText("Credential deleted.")).toBeVisible();
  });

  test("opens Add Credential dialog and submits new credential", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);

    await page.getByRole("button", { name: /Add Credential/i }).click();

    // Dialog should appear
    await expect(page.getByRole("dialog")).toBeVisible();

    await page.getByLabel(/Name/i).fill("MY_API_KEY");
    await page.getByLabel(/Value/i).fill("super-secret-value");

    // Submit
    await page.getByRole("button", { name: /^(add|save|submit|create)/i }).click();

    await expect(page.getByText("Credential added.")).toBeVisible();
  });

  test("Add Credential dialog rejects blank name", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);

    await page.getByRole("button", { name: /Add Credential/i }).click();
    await page.getByLabel(/Value/i).fill("some-value");
    await page.getByRole("button", { name: /^(add|save|submit|create)/i }).click();

    // Should show validation error
    await expect(page.getByText(/required/i)).toBeVisible();
  });

  test("Edit credential opens dialog with name read-only", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);

    await page.getByTestId("edit-GITHUB_TOKEN").click();

    await expect(page.getByRole("dialog")).toBeVisible();
    const nameInput = page.getByLabel(/Name/i);
    await expect(nameInput).toHaveValue("GITHUB_TOKEN");
    await expect(nameInput).toHaveAttribute("readonly", "");
  });

  test("Edit credential submits PUT and shows success toast", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);

    await page.getByTestId("edit-GITHUB_TOKEN").click();
    await page.getByLabel(/Value/i).fill("new-secret-value");
    await page.getByRole("button", { name: /^(save|update|submit)/i }).click();

    await expect(page.getByText("Credential updated.")).toBeVisible();
  });

  test("Add Binding dialog pre-fills store name with credential name", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);

    await page.getByTestId("expand-GITHUB_TOKEN").click();
    await page.getByRole("button", { name: /Add binding/i }).click();

    await expect(page.getByRole("dialog")).toBeVisible();
    const storeNameInput = page.getByLabel(/Store Name/i);
    await expect(storeNameInput).toHaveValue("GITHUB_TOKEN");
  });

  test("Add Binding submits and shows success toast", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);

    await page.getByTestId("expand-GITHUB_TOKEN").click();
    await page.getByRole("button", { name: /Add binding/i }).click();

    await page.getByLabel(/Logical Key/i).fill("GH");
    await page.getByRole("button", { name: /^(add|save|submit|create)/i }).click();

    await expect(page.getByText("Binding added.")).toBeVisible();
  });

  test("shows LoginDialog when server returns 401", async ({ page }) => {
    // First mock 401 responses
    await mockCredentialApis(page, { status401: true });
    await goToCredentials(page);

    // LoginDialog should appear (no close button)
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByLabel(/Username/i)).toBeVisible();
    await expect(page.getByLabel(/Password/i)).toBeVisible();
  });

  test("LoginDialog cannot be dismissed (no close button / ESC)", async ({ page }) => {
    await mockCredentialApis(page, { status401: true });
    await goToCredentials(page);

    await expect(page.getByRole("dialog")).toBeVisible();

    // ESC should not close
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeVisible();
  });

  test("LoginDialog shows error on bad credentials", async ({ page }) => {
    await mockCredentialApis(page, { status401: true });

    // Mock login endpoint to also return 401
    await page.route("**/api/auth/login", (route) =>
      route.fulfill({ status: 401, json: { message: "Invalid credentials" } }),
    );

    await goToCredentials(page);

    await page.getByLabel(/Username/i).fill("admin");
    await page.getByLabel(/Password/i).fill("wrongpassword");
    await page.getByRole("button", { name: /^(log in|login|sign in)/i }).click();

    await expect(page.getByText(/Invalid username or password/i)).toBeVisible();
  });

  test("LoginDialog on successful login stores token and loads credentials", async ({ page }) => {
    // First page load: 401. After login: 200.
    let authenticated = false;

    await page.route("**/api/credentials", async (route) => {
      if (route.request().method() === "GET") {
        if (!authenticated) {
          return route.fulfill({ status: 401, body: JSON.stringify({ message: "Unauthorized" }) });
        }
        return route.fulfill({ json: CREDENTIALS });
      }
      return route.continue();
    });
    await page.route("**/api/credentials/bindings", async (route) => {
      if (!authenticated) {
        return route.fulfill({ status: 401, body: JSON.stringify({ message: "Unauthorized" }) });
      }
      return route.fulfill({ json: [] });
    });
    await page.route("**/api/auth/login", async (route) => {
      authenticated = true;
      return route.fulfill({ json: { token: "test-jwt-token", user: { id: "1", username: "admin", name: "Admin" } } });
    });

    await goToCredentials(page);

    // Should show login dialog
    await expect(page.getByRole("dialog")).toBeVisible();

    await page.getByLabel(/Username/i).fill("admin");
    await page.getByLabel(/Password/i).fill("secret");
    await page.getByRole("button", { name: /^(log in|login|sign in)/i }).click();

    // Dialog should close and credentials load
    await expect(page.getByText("GITHUB_TOKEN")).toBeVisible();
  });

  test("OSS mode — no LoginDialog when server returns 200 without token", async ({ page }) => {
    // Simulate auth.enabled=false: server responds 200 normally, no token in localStorage
    await mockCredentialApis(page);
    await goToCredentials(page);

    // LoginDialog must NOT appear
    await expect(page.getByLabel(/Username/i)).not.toBeVisible();
    await expect(page.getByText("GITHUB_TOKEN")).toBeVisible();
  });

  test("Logout button visible only when token is stored", async ({ page }) => {
    await mockCredentialApis(page);
    await page.addInitScript(() => {
      localStorage.setItem("agentspan.credential_token", "some-jwt-token");
    });
    await goToCredentials(page);

    await expect(page.getByRole("button", { name: /logout/i })).toBeVisible();
  });

  test("Logout button not shown in OSS mode (no token)", async ({ page }) => {
    await mockCredentialApis(page);
    await goToCredentials(page);

    await expect(page.getByRole("button", { name: /logout/i })).not.toBeVisible();
  });

  test("clicking Logout clears token and hides Logout button", async ({ page }) => {
    await mockCredentialApis(page);
    await page.addInitScript(() => {
      localStorage.setItem("agentspan.credential_token", "some-jwt-token");
    });
    await goToCredentials(page);

    await page.getByRole("button", { name: /logout/i }).click();
    await expect(page.getByRole("button", { name: /logout/i })).not.toBeVisible();

    // Token should be cleared from localStorage
    const token = await page.evaluate(() => localStorage.getItem("agentspan.credential_token"));
    expect(token).toBeNull();
  });
});
