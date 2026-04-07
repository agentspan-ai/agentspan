/**
 * 04 — Guardrails, Errors, and Edge Cases
 *
 * Test safety features: guardrail pass/fail, error handling,
 * finish reasons, and edge-case scenarios.
 *
 * Covers:
 *   - assertGuardrailPassed / assertGuardrailFailed
 *   - guardrailPassed() / guardrailFailed() in fluent API
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
  MockEvent,
  mockRun,
  expect as agentExpect,
  assertStatus,
  assertNoErrors,
  assertToolUsed,
  assertGuardrailPassed,
  assertGuardrailFailed,
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
  it("blocks PII requests with guardrail_fail event", () => {
    const result = mockRun(
      supportAgent,
      "Give me Alice's SSN and credit card number",
      {
        events: [
          MockEvent.guardrailFail("pii_detector", "PII request detected"),
          MockEvent.done({ result: "I cannot share sensitive personal information." }),
        ],
      },
    );

    assertGuardrailFailed(result, "pii_detector");
    assertStatus(result, "COMPLETED");
  });

  it("passes safe requests through guardrail", () => {
    const result = mockRun(
      supportAgent,
      "What's my account status?",
      {
        events: [
          MockEvent.guardrailPass("pii_detector", "clean"),
          MockEvent.toolCall("query_user_data", { userId: "U-123" }),
          MockEvent.toolResult("query_user_data", {
            userId: "U-123",
            status: "active",
          }),
          MockEvent.done({ result: "Your account is active." }),
        ],
      },
    );

    assertGuardrailPassed(result, "pii_detector");
    assertToolUsed(result, "query_user_data");
    assertNoErrors(result);
  });
});

describe("Output Guardrails", () => {
  it("guardrail pass event is recorded", () => {
    const result = mockRun(supportAgent, "Update my email", {
      events: [
        MockEvent.guardrailPass("output_sanitizer"),
        MockEvent.toolCall("update_user", {
          userId: "U-123",
          field: "email",
          value: "new@example.com",
        }),
        MockEvent.toolResult("update_user", "Email updated successfully"),
        MockEvent.done({ result: "Email updated." }),
      ],
    });

    assertToolUsed(result, "update_user");
    assertGuardrailPassed(result, "output_sanitizer");
    agentExpect(result).completed();
  });

  it("validates guardrails with fluent API", () => {
    const result = mockRun(supportAgent, "Simple question", {
      events: [
        MockEvent.guardrailPass("pii_detector"),
        MockEvent.done({ result: "Here you go." }),
      ],
    });

    agentExpect(result)
      .completed()
      .guardrailPassed("pii_detector")
      .noErrors();
  });
});

// ═════════════════════════════════════════════════════════════════════
// 2. ERROR HANDLING
// ═════════════════════════════════════════════════════════════════════

describe("Error Handling", () => {
  it("handles tool error events", () => {
    const result = mockRun(supportAgent, "Look up user XYZ", {
      events: [
        MockEvent.toolCall("query_user_data", { userId: "XYZ" }),
        MockEvent.error("User not found in database"),
      ],
    });

    assertStatus(result, "FAILED");
    expect(() => assertNoErrors(result)).toThrow();
  });

  it("detects error events in the trace", () => {
    const result = mockRun(supportAgent, "Crash please", {
      events: [
        MockEvent.toolCall("query_user_data", { userId: "crash" }),
        MockEvent.error("Connection timeout"),
      ],
    });

    const errorEvents = result.events.filter((e) => e.type === "error");
    expect(errorEvents).toHaveLength(1);
    expect(errorEvents[0].content).toBe("Connection timeout");
  });

  it("error event sets FAILED status", () => {
    const failAgent = new Agent({
      name: "fail-agent",
      model: "openai/gpt-4o",
      instructions: "Always fail.",
    });

    const result = mockRun(failAgent, "Do the impossible", {
      events: [MockEvent.error("Cannot comply")],
    });

    assertStatus(result, "FAILED");
  });
});

// ═════════════════════════════════════════════════════════════════════
// 3. THINKING AND WAITING EVENTS
// ═════════════════════════════════════════════════════════════════════

describe("Thinking and Waiting Events", () => {
  it("thinking events are captured", () => {
    const result = mockRun(supportAgent, "Quick question", {
      events: [
        MockEvent.thinking("Processing the request..."),
        MockEvent.done({ result: "Here's your answer." }),
      ],
    });

    agentExpect(result)
      .completed()
      .eventsContain("thinking");
  });

  it("waiting events indicate human-in-the-loop", () => {
    const result = mockRun(supportAgent, "Need approval", {
      events: [
        MockEvent.waiting("Awaiting manager approval"),
        MockEvent.done({ result: "Approved." }),
      ],
    });

    agentExpect(result)
      .completed()
      .eventsContain("waiting");
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
  it("safe request routes to safe handler", () => {
    const result = mockRun(gatedSupport, "Show me my profile", {
      events: [
        MockEvent.guardrailPass("safety_check"),
        MockEvent.handoff("safe-handler"),
        MockEvent.toolCall("query_user_data", { userId: "U-456" }),
        MockEvent.toolResult("query_user_data", {
          name: "Alice",
          email: "alice@example.com",
        }),
        MockEvent.done({ result: "Here's your profile." }),
      ],
    });

    assertHandoffTo(result, "safe-handler");
    assertToolUsed(result, "query_user_data");
    assertNoErrors(result);
  });

  it("risky handler runs directly when targeted", () => {
    const result = mockRun(riskyHandler, "Update my display name to Bob", {
      events: [
        MockEvent.toolCall("update_user", {
          userId: "U-456",
          field: "name",
          value: "Bob",
        }),
        MockEvent.toolResult("update_user", "Updated name to Bob"),
        MockEvent.done({ result: "Name updated to Bob." }),
      ],
    });

    assertToolUsed(result, "update_user");
    assertNoErrors(result);
  });

  it("both paths complete without errors", () => {
    // Safe path
    const safeResult = mockRun(gatedSupport, "What's my account status?", {
      events: [
        MockEvent.handoff("safe-handler"),
        MockEvent.toolCall("query_user_data", { userId: "U-789" }),
        MockEvent.toolResult("query_user_data", { status: "active" }),
        MockEvent.done({ result: "Active." }),
      ],
    });
    assertNoErrors(safeResult);

    // Risky path
    const riskyResult = mockRun(gatedSupport, "Delete my account", {
      events: [
        MockEvent.handoff("risky-handler"),
        MockEvent.toolCall("delete_account", { userId: "U-789" }),
        MockEvent.toolResult("delete_account", "Account deleted"),
        MockEvent.done({ result: "Account deleted." }),
      ],
    });
    assertNoErrors(riskyResult);
  });
});
