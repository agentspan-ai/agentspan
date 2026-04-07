/**
 * 05 — Advanced Patterns
 *
 * Record/replay for regression tests, strategy validation,
 * nested agent strategies, and complex multi-agent compositions.
 *
 * Covers:
 *   - record() / replay() for fixture-based testing
 *   - validateStrategy() for structural trace checks
 *   - Nested agent strategies
 *   - Complex tool interaction patterns
 *   - Event sequence assertions
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
  MockEvent,
  mockRun,
  expect as agentExpect,
  record,
  replay,
  validateStrategy,
  assertAgentRan,
  assertHandoffTo,
  assertToolUsed,
  assertNoErrors,
  assertStatus,
  assertEventSequence,
  assertToolCallOrder,
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
  it("records a result to a fixture file and replays it", () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "agentspan-test-"));
    const fixturePath = path.join(tmpDir, "shipping-run.json");

    try {
      // Create a result with scripted events
      const result = mockRun(shippingAgent, "Track my package TRK-001", {
        events: [
          MockEvent.toolCall("track_shipment", { trackingId: "TRK-001" }),
          MockEvent.toolResult("track_shipment", {
            trackingId: "TRK-001",
            status: "delivered",
          }),
          MockEvent.done({ result: "Package TRK-001 has been delivered." }),
        ],
      });

      agentExpect(result).completed();
      assertToolUsed(result, "track_shipment");

      // Record to fixture file
      record(result, fixturePath);

      // Verify fixture file was created
      expect(fs.existsSync(fixturePath)).toBe(true);

      // Replay from the fixture
      const replayed = replay(fixturePath);

      // Same assertions pass on the replayed result
      agentExpect(replayed).completed();
      assertToolUsed(replayed, "track_shipment");
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  it("replayed result preserves events and tool calls", () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "agentspan-test-"));
    const fixturePath = path.join(tmpDir, "inventory-run.json");

    try {
      const original = mockRun(inventoryAgent, "Is item X in stock?", {
        events: [
          MockEvent.toolCall("check_inventory", { productId: "X" }),
          MockEvent.toolResult("check_inventory", {
            productId: "X",
            inStock: true,
            quantity: 50,
          }),
          MockEvent.done({ result: "Yes, 50 units in stock." }),
        ],
      });

      record(original, fixturePath);
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
  it("validates handoff strategy against trace", () => {
    const result = mockRun(ecommerceSupport, "Track my package", {
      events: [
        MockEvent.handoff("shipping-specialist"),
        MockEvent.done({ result: "Tracked." }),
      ],
    });

    expect(() => validateStrategy(ecommerceSupport, result)).not.toThrow();
  });

  it("validates parallel strategy against trace", () => {
    const parallelTeam = new Agent({
      name: "parallel-team",
      model: "openai/gpt-4o",
      agents: [inventoryAgent, shippingAgent],
      strategy: "parallel",
    });

    const result = mockRun(parallelTeam, "Check both", {
      events: [
        MockEvent.handoff("inventory-specialist"),
        MockEvent.handoff("shipping-specialist"),
        MockEvent.done({ result: "Both checked." }),
      ],
    });

    expect(() => validateStrategy(parallelTeam, result)).not.toThrow();
  });

  it("validates sequential strategy against trace", () => {
    const sequentialPipeline = new Agent({
      name: "sequential-pipeline",
      model: "openai/gpt-4o",
      agents: [inventoryAgent, returnsAgent],
      strategy: "sequential",
    });

    const result = mockRun(sequentialPipeline, "Check then process", {
      events: [
        MockEvent.handoff("inventory-specialist"),
        MockEvent.handoff("returns-specialist"),
        MockEvent.done({ result: "Done." }),
      ],
    });

    expect(() => validateStrategy(sequentialPipeline, result)).not.toThrow();
  });

  it("throws on strategy violation", () => {
    // Sequential pipeline but only one agent ran
    const sequentialPipeline = new Agent({
      name: "sequential-pipeline",
      model: "openai/gpt-4o",
      agents: [inventoryAgent, returnsAgent],
      strategy: "sequential",
    });

    const result = mockRun(sequentialPipeline, "Partial run", {
      events: [
        MockEvent.handoff("inventory-specialist"),
        MockEvent.done({ result: "Only one ran." }),
      ],
    });

    expect(() => validateStrategy(sequentialPipeline, result)).toThrow();
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
  it("parallel research feeds into sequential report writing", () => {
    const result = mockRun(researchPipeline, "Analyze the cloud computing market", {
      events: [
        MockEvent.handoff("research-phase"),
        MockEvent.handoff("market-researcher"),
        MockEvent.handoff("competitor-analyst"),
        MockEvent.handoff("report-writer"),
        MockEvent.done({ result: "Market analysis report complete." }),
      ],
    });

    assertAgentRan(result, "market-researcher");
    assertAgentRan(result, "competitor-analyst");
    assertAgentRan(result, "report-writer");
    assertNoErrors(result);
  });

  it("validates outer sequential strategy", () => {
    const result = mockRun(researchPipeline, "Analyze something", {
      events: [
        MockEvent.handoff("research-phase"),
        MockEvent.handoff("report-writer"),
        MockEvent.done({ result: "Done." }),
      ],
    });

    expect(() => validateStrategy(researchPipeline, result)).not.toThrow();
  });
});

// ═════════════════════════════════════════════════════════════════════
// 4. COMPLEX TOOL INTERACTION PATTERNS
// ═════════════════════════════════════════════════════════════════════

describe("Complex Tool Patterns", () => {
  it("tracks tool call ordering with assertToolCallOrder", () => {
    const multiToolAgent = new Agent({
      name: "multi-tool-agent",
      model: "openai/gpt-4o",
      instructions: "Check inventory then track shipment.",
      tools: [checkInventory, trackShipment],
    });

    const result = mockRun(
      multiToolAgent,
      "Check stock for item P-1 and track shipment TRK-P1",
      {
        events: [
          MockEvent.toolCall("check_inventory", { productId: "P-1" }),
          MockEvent.toolResult("check_inventory", { productId: "P-1", inStock: true, quantity: 10 }),
          MockEvent.toolCall("track_shipment", { trackingId: "TRK-P1" }),
          MockEvent.toolResult("track_shipment", { trackingId: "TRK-P1", status: "shipped" }),
          MockEvent.done({ result: "Item P-1 in stock; TRK-P1 shipped." }),
        ],
      },
    );

    assertToolUsed(result, "check_inventory");
    assertToolUsed(result, "track_shipment");
    assertToolCallOrder(result, ["check_inventory", "track_shipment"]);
  });

  it("handles concurrent tool calls in parallel agents", () => {
    const parallelTools = new Agent({
      name: "parallel-tools",
      model: "openai/gpt-4o",
      agents: [inventoryAgent, shippingAgent],
      strategy: "parallel",
    });

    const result = mockRun(
      parallelTools,
      "Check inventory and track shipment simultaneously",
      {
        events: [
          MockEvent.handoff("inventory-specialist"),
          MockEvent.toolCall("check_inventory", { productId: "X" }),
          MockEvent.toolResult("check_inventory", { inStock: true }),
          MockEvent.handoff("shipping-specialist"),
          MockEvent.toolCall("track_shipment", { trackingId: "TRK-1" }),
          MockEvent.toolResult("track_shipment", { status: "delivered" }),
          MockEvent.done({ result: "Both checked." }),
        ],
      },
    );

    assertAgentRan(result, "inventory-specialist");
    assertAgentRan(result, "shipping-specialist");
    assertNoErrors(result);
  });
});

// ═════════════════════════════════════════════════════════════════════
// 5. EVENT SEQUENCE ASSERTIONS
// ═════════════════════════════════════════════════════════════════════

describe("Event Sequence Assertions", () => {
  it("verifies event type subsequence", () => {
    const result = mockRun(inventoryAgent, "Check stock", {
      events: [
        MockEvent.thinking("Let me check..."),
        MockEvent.toolCall("check_inventory", { productId: "Y" }),
        MockEvent.toolResult("check_inventory", { inStock: true }),
        MockEvent.done({ result: "In stock." }),
      ],
    });

    assertEventSequence(result, ["thinking", "tool_call", "tool_result", "done"]);
  });
});
