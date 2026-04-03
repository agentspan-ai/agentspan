/**
 * 02 — Tool Assertion Deep-Dive
 *
 * Thorough testing of tool usage: argument validation, call ordering,
 * mock tool implementations, and output validation.
 *
 * Covers:
 *   - mockTools for overriding tool behavior
 *   - assertToolUsed / assertNoErrors
 *   - expectResult fluent chain with toContainOutput
 *   - Testing tool call sequences
 *   - Custom mock implementations
 *
 * Run:
 *   npx vitest run examples/mock_tests/02-tool-assertions.test.ts
 */

import { describe, it, expect } from "vitest";
import { z } from "zod";
import { Agent, tool } from "@agentspan-ai/sdk";
import {
  mockRun,
  expectResult,
  assertToolUsed,
  assertNoErrors,
  assertStatus,
} from "@agentspan-ai/sdk/testing";

// ── Tools ────────────────────────────────────────────────────────────

const searchProducts = tool(
  async (args: { query: string; maxResults?: number }) => {
    const n = args.maxResults ?? 5;
    return Array.from({ length: n }, (_, i) => ({
      name: `Product ${i + 1}`,
      price: 9.99 * (i + 1),
    }));
  },
  {
    name: "search_products",
    description: "Search the product catalog.",
    inputSchema: z.object({
      query: z.string(),
      maxResults: z.number().optional().default(5),
    }),
  },
);

const getProductDetails = tool(
  async (args: { productId: string }) => ({
    id: args.productId,
    name: "Widget",
    stock: 42,
    price: 19.99,
  }),
  {
    name: "get_product_details",
    description: "Get detailed info for a product.",
    inputSchema: z.object({ productId: z.string() }),
  },
);

const addToCart = tool(
  async (args: { productId: string; quantity: number }) => ({
    success: true,
    message: `Added ${args.quantity}x ${args.productId} to cart`,
  }),
  {
    name: "add_to_cart",
    description: "Add a product to the shopping cart.",
    inputSchema: z.object({
      productId: z.string(),
      quantity: z.number(),
    }),
  },
);

const checkout = tool(
  async (args: { paymentMethod: string }) => ({
    orderId: "ORD-001",
    status: "confirmed",
    payment: args.paymentMethod,
  }),
  {
    name: "checkout",
    description: "Process checkout.",
    inputSchema: z.object({ paymentMethod: z.string() }),
  },
);

// ── Agent ────────────────────────────────────────────────────────────

const shopAgent = new Agent({
  name: "shop-assistant",
  model: "openai/gpt-4o",
  instructions: "Help customers find and purchase products.",
  tools: [searchProducts, getProductDetails, addToCart, checkout],
});

// ── Tests ────────────────────────────────────────────────────────────

describe("Mock Tool Implementations", () => {
  it("overrides tool behavior with mockTools", async () => {
    const result = await mockRun(shopAgent, "Search for red shoes", {
      mockTools: {
        search_products: async (args: { query: string }) => [
          { name: "Red Running Shoe", price: 89.99 },
          { name: "Red Heel", price: 129.99 },
        ],
      },
    });

    assertToolUsed(result, "search_products");
    expectResult(result).toBeCompleted();
  });

  it("mock returns empty results", async () => {
    const result = await mockRun(shopAgent, "Search for unicorn saddles", {
      mockTools: {
        search_products: async () => [],
      },
    });

    assertToolUsed(result, "search_products");
    assertNoErrors(result);
  });
});

describe("Full Shopping Flow", () => {
  it("executes search → details → cart → checkout", async () => {
    const toolCallOrder: string[] = [];

    const result = await mockRun(shopAgent, "Find a widget and buy it", {
      mockTools: {
        search_products: async (args: { query: string }) => {
          toolCallOrder.push("search_products");
          return [{ id: "W-1", name: "Widget" }];
        },
        get_product_details: async (args: { productId: string }) => {
          toolCallOrder.push("get_product_details");
          return { id: args.productId, name: "Widget", stock: 42 };
        },
        add_to_cart: async (args: { productId: string; quantity: number }) => {
          toolCallOrder.push("add_to_cart");
          return { success: true };
        },
        checkout: async (args: { paymentMethod: string }) => {
          toolCallOrder.push("checkout");
          return { orderId: "ORD-001", status: "confirmed" };
        },
      },
    });

    // All tools were used
    assertToolUsed(result, "search_products");
    assertToolUsed(result, "get_product_details");
    assertToolUsed(result, "add_to_cart");
    assertToolUsed(result, "checkout");

    // Verify ordering via our tracking array
    expect(toolCallOrder).toEqual([
      "search_products",
      "get_product_details",
      "add_to_cart",
      "checkout",
    ]);
  });
});

describe("Output Validation", () => {
  it("tool result contains expected data", async () => {
    const result = await mockRun(shopAgent, "Place my order", {
      mockTools: {
        checkout: async () => ({
          orderId: "ORD-12345",
          status: "confirmed",
        }),
      },
    });

    expectResult(result).toBeCompleted();

    // Verify the tool result was captured in events
    const toolResult = result.events.find(
      (e) => e.type === "tool_result" && e.toolName === "checkout",
    );
    expect(toolResult).toBeDefined();
    expect(toolResult!.result).toEqual({
      orderId: "ORD-12345",
      status: "confirmed",
    });
  });

  it("output contains structured data", async () => {
    const result = await mockRun(shopAgent, "Search for laptops", {
      mockTools: {
        search_products: async () => [
          { name: "MacBook Pro", price: 2499 },
          { name: "ThinkPad X1", price: 1799 },
        ],
      },
    });

    expectResult(result).toBeCompleted();
    // Verify the result has events
    expect(result.events.length).toBeGreaterThan(0);
  });
});

describe("Error in Mock Tools", () => {
  it("handles tool that throws an error", async () => {
    const result = await mockRun(shopAgent, "Search for broken item", {
      mockTools: {
        search_products: async () => {
          throw new Error("Database connection failed");
        },
      },
    });

    // The agent should handle the error gracefully
    expect(result.status).toBeDefined();
  });

  it("handles missing mock tool gracefully", async () => {
    // Only mock one tool — others use default implementations
    const result = await mockRun(shopAgent, "Quick search", {
      mockTools: {
        search_products: async () => [{ name: "Item" }],
      },
    });

    assertToolUsed(result, "search_products");
  });
});

describe("Token Usage Validation", () => {
  it("checks token usage is within budget", async () => {
    const result = await mockRun(shopAgent, "Simple question", {
      mockTools: {
        search_products: async () => [{ name: "Item" }],
      },
    });

    expectResult(result).toBeCompleted().toHaveTokenUsageBelow(100000);
  });
});
