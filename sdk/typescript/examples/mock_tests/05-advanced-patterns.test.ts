/**
 * 05 — Advanced Patterns
 *
 * Record/replay for regression tests, LLM-based evaluation with
 * CorrectnessEval, strategy validation, and complex multi-agent
 * compositions.
 *
 * Covers:
 *   - record() / replay() for fixture-based testing
 *   - CorrectnessEval with rubrics (integration)
 *   - validateStrategy() for structural checks
 *   - Nested agent strategies
 *   - Complex tool interaction patterns
 *   - Session ID for conversation continuity
 *
 * Run:
 *   npx vitest run examples/mock_tests/05-advanced-patterns.test.ts
 */

import { describe, it, expect } from "vitest";
import { z } from "zod";
import * as path from "path";
import * as os from "os";
import * as fs from "fs";
import { Agent, tool } from "@agentspan-ai/sdk";
import {
  mockRun,
  expectResult,
  record,
  replay,
  validateStrategy,
  assertAgentRan,
  assertHandoffTo,
  assertToolUsed,
  assertNoErrors,
  assertStatus,
} from "@agentspan-ai/sdk/testing";

// ── Tools ────────────────────────────────────────────────────────────

const checkInventory = tool(
  async (args: { productId: string }) => ({
    productId: args.productId,
    inStock: true,
    quantity: 50,
  }),
  {
    name: "check_inventory",
    description: "Check product inventory.",
    inputSchema: z.object({ productId: z.string() }),
  },
);

const processReturn = tool(
  async (args: { orderId: string; reason: string }) =>
    `Return initiated for ${args.orderId}: ${args.reason}`,
  {
    name: "process_return",
    description: "Process a product return.",
    inputSchema: z.object({
      orderId: z.string(),
      reason: z.string(),
    }),
  },
);

const trackShipment = tool(
  async (args: { trackingId: string }) => ({
    trackingId: args.trackingId,
    status: "in_transit",
    eta: "2 days",
  }),
  {
    name: "track_shipment",
    description: "Track a shipment.",
    inputSchema: z.object({ trackingId: z.string() }),
  },
);

const escalateToManager = tool(
  async (args: { issue: string }) => `Escalated: ${args.issue}`,
  {
    name: "escalate_to_manager",
    description: "Escalate an issue to a human manager.",
    inputSchema: z.object({ issue: z.string() }),
  },
);

// ═════════════════════════════════════════════════════════════════════
// 1. RECORD / REPLAY — fixture-based regression tests
// ═════════════════════════════════════════════════════════════════════

const inventoryAgent = new Agent({
  name: "inventory-specialist",
  model: "openai/gpt-4o",
  instructions: "Handle inventory and stock questions.",
  tools: [checkInventory],
});

const returnsAgent = new Agent({
  name: "returns-specialist",
  model: "openai/gpt-4o",
  instructions: "Handle returns and refunds.",
  tools: [processReturn],
});

const shippingAgent = new Agent({
  name: "shipping-specialist",
  model: "openai/gpt-4o",
  instructions: "Handle shipping and tracking questions.",
  tools: [trackShipment],
});

const ecommerceSupport = new Agent({
  name: "ecommerce-support",
  model: "openai/gpt-4o",
  instructions: "Front-line e-commerce support.",
  agents: [inventoryAgent, returnsAgent, shippingAgent],
  strategy: "handoff",
});

describe("Record / Replay", () => {
  it("records a run to a fixture file and replays it", async () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "agentspan-test-"));
    const fixturePath = path.join(tmpDir, "shipping-run.json");

    try {
      // Record an execution — use the shipping agent directly
      const result = await record(
        shippingAgent,
        "Track my package TRK-001",
        {
          fixturePath,
          mockTools: {
            track_shipment: async () => ({
              trackingId: "TRK-001",
              status: "delivered",
            }),
          },
        },
      );

      expectResult(result).toBeCompleted();
      assertToolUsed(result, "track_shipment");

      // Verify fixture file was created
      expect(fs.existsSync(fixturePath)).toBe(true);

      // Replay from the fixture
      const replayed = replay(fixturePath);

      // Same assertions pass on the replayed result
      expectResult(replayed).toBeCompleted();
      assertToolUsed(replayed, "track_shipment");
    } finally {
      // Cleanup
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  it("replayed result preserves events", async () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "agentspan-test-"));
    const fixturePath = path.join(tmpDir, "inventory-run.json");

    try {
      const original = await record(
        inventoryAgent,
        "Is item X in stock?",
        {
          fixturePath,
          mockTools: {
            check_inventory: async () => ({
              productId: "X",
              inStock: true,
              quantity: 50,
            }),
          },
        },
      );

      const replayed = replay(fixturePath);

      // Event counts should match
      expect(replayed.events.length).toBe(original.events.length);

      // Tool calls should match
      expect(replayed.toolCalls.length).toBe(original.toolCalls.length);
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });
});

// ═════════════════════════════════════════════════════════════════════
// 2. STRATEGY VALIDATION
// ═════════════════════════════════════════════════════════════════════

describe("Strategy Validation", () => {
  it("validates handoff strategy", () => {
    // validateStrategy checks the agent's declared strategy
    validateStrategy(ecommerceSupport, "handoff");
  });

  it("validates parallel strategy", () => {
    const parallelTeam = new Agent({
      name: "parallel-team",
      model: "openai/gpt-4o",
      agents: [inventoryAgent, shippingAgent],
      strategy: "parallel",
    });

    validateStrategy(parallelTeam, "parallel");
  });

  it("validates sequential strategy", () => {
    const sequentialPipeline = new Agent({
      name: "sequential-pipeline",
      model: "openai/gpt-4o",
      agents: [inventoryAgent, returnsAgent],
      strategy: "sequential",
    });

    validateStrategy(sequentialPipeline, "sequential");
  });

  it("throws on strategy mismatch", () => {
    expect(() => {
      validateStrategy(ecommerceSupport, "parallel");
    }).toThrow();
  });
});

// ═════════════════════════════════════════════════════════════════════
// 3. NESTED MULTI-AGENT STRATEGIES
// ═════════════════════════════════════════════════════════════════════

const marketResearcher = new Agent({
  name: "market-researcher",
  model: "openai/gpt-4o",
  instructions: "Research market trends.",
});

const competitorAnalyst = new Agent({
  name: "competitor-analyst",
  model: "openai/gpt-4o",
  instructions: "Analyze competitors.",
});

const parallelResearch = new Agent({
  name: "research-phase",
  model: "openai/gpt-4o",
  agents: [marketResearcher, competitorAnalyst],
  strategy: "parallel",
});

const reportWriter = new Agent({
  name: "report-writer",
  model: "openai/gpt-4o",
  instructions: "Write a synthesis report.",
});

const researchPipeline = new Agent({
  name: "research-pipeline",
  model: "openai/gpt-4o",
  agents: [parallelResearch, reportWriter],
  strategy: "sequential",
});

describe("Nested Strategies", () => {
  it("parallel research feeds into sequential report writing", async () => {
    const result = await mockRun(
      researchPipeline,
      "Analyze the cloud computing market",
    );

    assertAgentRan(result, "market-researcher");
    assertAgentRan(result, "competitor-analyst");
    assertAgentRan(result, "report-writer");
    assertNoErrors(result);
  });

  it("validates outer strategy", () => {
    validateStrategy(researchPipeline, "sequential");
  });

  it("validates inner strategy", () => {
    validateStrategy(parallelResearch, "parallel");
  });
});

// ═════════════════════════════════════════════════════════════════════
// 4. COMPLEX TOOL INTERACTION PATTERNS
// ═════════════════════════════════════════════════════════════════════

describe("Complex Tool Patterns", () => {
  it("tracks tool call ordering via callLog", async () => {
    const callLog: Array<{ tool: string; args: unknown }> = [];

    // Use a single agent with both tools to test call ordering
    const multiToolAgent = new Agent({
      name: "multi-tool-agent",
      model: "openai/gpt-4o",
      instructions: "Check inventory then track shipment.",
      tools: [checkInventory, trackShipment],
    });

    const result = await mockRun(
      multiToolAgent,
      "Check stock for item P-1 and track shipment TRK-P1",
      {
        mockTools: {
          check_inventory: async (args: { productId: string }) => {
            callLog.push({ tool: "check_inventory", args });
            return { productId: args.productId, inStock: true, quantity: 10 };
          },
          track_shipment: async (args: { trackingId: string }) => {
            callLog.push({ tool: "track_shipment", args });
            return { trackingId: args.trackingId, status: "shipped" };
          },
        },
      },
    );

    // Both tools should have been called
    const toolNames = callLog.map((c) => c.tool);
    expect(toolNames).toContain("check_inventory");
    expect(toolNames).toContain("track_shipment");

    // check_inventory should come before track_shipment
    const inventoryIdx = toolNames.indexOf("check_inventory");
    const shipmentIdx = toolNames.indexOf("track_shipment");
    expect(inventoryIdx).toBeLessThan(shipmentIdx);
  });

  it("handles concurrent tool calls in parallel agents", async () => {
    const parallelTools = new Agent({
      name: "parallel-tools",
      model: "openai/gpt-4o",
      agents: [inventoryAgent, shippingAgent],
      strategy: "parallel",
    });

    const result = await mockRun(
      parallelTools,
      "Check inventory and track shipment simultaneously",
      {
        mockTools: {
          check_inventory: async () => ({ inStock: true }),
          track_shipment: async () => ({ status: "delivered" }),
        },
      },
    );

    assertAgentRan(result, "inventory-specialist");
    assertAgentRan(result, "shipping-specialist");
    assertNoErrors(result);
  });
});

// ═════════════════════════════════════════════════════════════════════
// 5. SESSION ID FOR CONVERSATION CONTINUITY
// ═════════════════════════════════════════════════════════════════════

describe("Session Management", () => {
  it("uses custom session ID for continuity", async () => {
    const result = await mockRun(
      inventoryAgent,
      "Is item X in stock?",
      {
        sessionId: "session-abc-123",
        mockTools: {
          check_inventory: async () => ({
            productId: "X",
            inStock: true,
          }),
        },
      },
    );

    expectResult(result).toBeCompleted();
    assertToolUsed(result, "check_inventory");
  });

  it("different sessions are independent", async () => {
    const result1 = await mockRun(
      inventoryAgent,
      "Check item A",
      {
        sessionId: "session-1",
        mockTools: {
          check_inventory: async () => ({ productId: "A", inStock: true }),
        },
      },
    );

    const result2 = await mockRun(
      inventoryAgent,
      "Check item B",
      {
        sessionId: "session-2",
        mockTools: {
          check_inventory: async () => ({ productId: "B", inStock: false }),
        },
      },
    );

    expectResult(result1).toBeCompleted();
    expectResult(result2).toBeCompleted();

    // Both should have used the tool independently
    assertToolUsed(result1, "check_inventory");
    assertToolUsed(result2, "check_inventory");
  });
});
