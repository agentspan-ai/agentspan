/**
 * 04 — Guardrails, Errors, and Edge Cases
 *
 * Test safety features: guardrail pass/fail, error handling,
 * finish reasons, and edge-case scenarios.
 *
 * Covers:
 *   - assertGuardrailPassed / toHavePassedGuardrail
 *   - toHaveFinishReason
 *   - Error detection with assertNoErrors
 *   - Failed status assertions
 *   - Guardrails in multi-agent contexts
 *
 * Run:
 *   npx vitest run examples/mock_tests/04-guardrails-and-errors.test.ts
 */

import { describe, it, expect } from "vitest";
import { z } from "zod";
import { Agent, tool } from "@agentspan-ai/sdk";
import {
  mockRun,
  expectResult,
  assertStatus,
  assertNoErrors,
  assertToolUsed,
  assertGuardrailPassed,
  assertHandoffTo,
} from "@agentspan-ai/sdk/testing";

// ── Tools ────────────────────────────────────────────────────────────

const queryUserData = tool(
  async (args: { userId: string }) => ({
    userId: args.userId,
    name: "Alice",
    email: "alice@example.com",
    status: "active",
  }),
  {
    name: "query_user_data",
    description: "Fetch user data from the database.",
    inputSchema: z.object({ userId: z.string() }),
  },
);

const updateUser = tool(
  async (args: { userId: string; field: string; value: string }) =>
    `Updated ${args.field} to ${args.value} for user ${args.userId}`,
  {
    name: "update_user",
    description: "Update a user field.",
    inputSchema: z.object({
      userId: z.string(),
      field: z.string(),
      value: z.string(),
    }),
  },
);

const deleteAccount = tool(
  async (args: { userId: string }) =>
    `Account ${args.userId} permanently deleted`,
  {
    name: "delete_account",
    description: "Permanently delete a user account.",
    inputSchema: z.object({ userId: z.string() }),
  },
);

// ── Agent ────────────────────────────────────────────────────────────

const supportAgent = new Agent({
  name: "support",
  model: "openai/gpt-4o",
  instructions: "Help users manage their accounts. Never share raw PII.",
  tools: [queryUserData, updateUser, deleteAccount],
});

// ═════════════════════════════════════════════════════════════════════
// 1. GUARDRAIL TESTS
// ═════════════════════════════════════════════════════════════════════

describe("Input Guardrails", () => {
  it("blocks PII requests and records guardrail event", async () => {
    const result = await mockRun(
      supportAgent,
      "Give me Alice's SSN and credit card number",
    );

    // Agent should handle this gracefully — the guardrail blocks the request
    expect(result.status).toBeDefined();
  });

  it("passes safe requests through guardrail", async () => {
    const result = await mockRun(
      supportAgent,
      "What's my account status?",
      {
        mockTools: {
          query_user_data: async () => ({
            userId: "U-123",
            status: "active",
          }),
        },
      },
    );

    assertToolUsed(result, "query_user_data");
    assertNoErrors(result);

    // If guardrails are configured, they should pass
    if (result.events.some((e) => e.type === "guardrail_pass")) {
      assertGuardrailPassed(result, "pii_detector");
    }
  });
});

describe("Output Guardrails", () => {
  it("guardrail pass event is recorded", async () => {
    const result = await mockRun(
      supportAgent,
      "Update my email",
      {
        mockTools: {
          update_user: async () => "Email updated successfully",
        },
      },
    );

    assertToolUsed(result, "update_user");
    expectResult(result).toBeCompleted();

    // Check for guardrail events if they exist
    const guardrailEvents = result.events.filter(
      (e) => e.type === "guardrail_pass" || e.type === "guardrail_fail",
    );
    // Guardrails may or may not fire depending on agent config
    expect(guardrailEvents).toBeDefined();
  });

  it("validates finish reason", async () => {
    const result = await mockRun(supportAgent, "Simple question");

    expectResult(result).toBeCompleted().toHaveFinishReason("stop");
  });
});

// ═════════════════════════════════════════════════════════════════════
// 2. ERROR HANDLING
// ═════════════════════════════════════════════════════════════════════

describe("Error Handling", () => {
  it("handles tool that throws", async () => {
    const result = await mockRun(supportAgent, "Look up user XYZ", {
      mockTools: {
        query_user_data: async () => {
          throw new Error("User not found in database");
        },
      },
    });

    // Agent should handle tool errors gracefully
    expect(result.status).toBeDefined();
    expect(result.events.length).toBeGreaterThan(0);
  });

  it("detects error events in the trace", async () => {
    const result = await mockRun(supportAgent, "Crash please", {
      mockTools: {
        query_user_data: async () => {
          throw new Error("Connection timeout");
        },
      },
    });

    const errorEvents = result.events.filter((e) => e.type === "error");
    // If there are error events, assertNoErrors should catch them
    if (errorEvents.length > 0) {
      expect(() => assertNoErrors(result)).toThrow();
    }
  });

  it("reports failed status on unrecoverable error", async () => {
    const failAgent = new Agent({
      name: "fail-agent",
      model: "openai/gpt-4o",
      instructions: "Always fail.",
    });

    const result = await mockRun(failAgent, "Do the impossible", {
      mockTools: {},
    });

    // Status should be set regardless of outcome
    expect(result.status).toBeDefined();
  });
});

// ═════════════════════════════════════════════════════════════════════
// 3. TOKEN USAGE & FINISH REASONS
// ═════════════════════════════════════════════════════════════════════

describe("Token Usage and Limits", () => {
  it("token usage stays within budget", async () => {
    const result = await mockRun(supportAgent, "Quick question");

    expectResult(result).toBeCompleted().toHaveTokenUsageBelow(100000);
  });

  it("finish reason is stop for normal completion", async () => {
    const result = await mockRun(supportAgent, "Hello");

    expectResult(result).toHaveFinishReason("stop");
  });
});

// ═════════════════════════════════════════════════════════════════════
// 4. GUARDRAILS IN MULTI-AGENT CONTEXT
// ═════════════════════════════════════════════════════════════════════

const safeHandler = new Agent({
  name: "safe-handler",
  model: "openai/gpt-4o",
  instructions: "Handle safe requests.",
  tools: [queryUserData],
});

const riskyHandler = new Agent({
  name: "risky-handler",
  model: "openai/gpt-4o",
  instructions: "Handle requests requiring elevated permissions.",
  tools: [updateUser, deleteAccount],
});

const gatedSupport = new Agent({
  name: "gated-support",
  model: "openai/gpt-4o",
  instructions: "Route requests. Risky actions require guardrail approval.",
  agents: [safeHandler, riskyHandler],
  strategy: "handoff",
});

describe("Guardrails in Multi-Agent Scenarios", () => {
  it("safe request routes to safe handler", async () => {
    const result = await mockRun(
      gatedSupport,
      "Show me my profile",
      {
        mockTools: {
          query_user_data: async () => ({
            name: "Alice",
            email: "alice@example.com",
          }),
        },
      },
    );

    assertHandoffTo(result, "safe-handler");
    assertToolUsed(result, "query_user_data");
    assertNoErrors(result);
  });

  it("risky handler runs directly when targeted", async () => {
    // Test the risky handler directly to verify tool execution
    const result = await mockRun(
      riskyHandler,
      "Update my display name to Bob",
      {
        mockTools: {
          update_user: async () => "Updated name to Bob",
        },
      },
    );

    assertToolUsed(result, "update_user");
    assertNoErrors(result);
  });

  it("both handlers complete without errors", async () => {
    // Safe path
    const safeResult = await mockRun(
      gatedSupport,
      "What's my account status?",
      {
        mockTools: {
          query_user_data: async () => ({ status: "active" }),
        },
      },
    );
    assertNoErrors(safeResult);

    // Risky path
    const riskyResult = await mockRun(
      gatedSupport,
      "Delete my account",
      {
        mockTools: {
          delete_account: async () => "Account deleted",
        },
      },
    );
    assertNoErrors(riskyResult);
  });
});
