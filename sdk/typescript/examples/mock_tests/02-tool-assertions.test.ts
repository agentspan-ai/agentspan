/**
 * 02 — Tool Assertion Deep-Dive
 *
 * Thorough testing of tool usage: argument validation, call ordering,
 * tool assertion functions, and output validation.
 *
 * Covers:
 *   - MockEvent for scripting tool call / result events
 *   - assertToolUsed / assertToolNotUsed / assertToolCalledWith
 *   - assertToolCallOrder / assertToolsUsedExactly
 *   - expect() fluent chain with outputContains
 *   - Testing tool call sequences
 *
 * Run:
 *   npx vitest run examples/mock_tests/02-tool-assertions.test.ts
 */

import { describe, it, expect } from "vitest";
import { z } from "zod";
import { Agent, tool } from "@agentspan-ai/sdk";
import {
  MockEvent,
  mockRun,
  expect as agentExpect,
  assertToolUsed,
  assertToolNotUsed,
  assertToolCalledWith,
  assertToolCallOrder,
  assertToolsUsedExactly,
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

describe("Tool Assertions", () => {
  it("assertToolUsed detects used tool", () => {
    const result = mockRun(shopAgent, "Search for red shoes", {
      events: [
        MockEvent.toolCall("search_products", { query: "red shoes" }),
        MockEvent.toolResult("search_products", [
          { name: "Red Running Shoe", price: 89.99 },
          { name: "Red Heel", price: 129.99 },
        ]),
        MockEvent.done({ result: "Found 2 red shoes." }),
      ],
    });

    assertToolUsed(result, "search_products");
    agentExpect(result).completed();
  });

  it("assertToolNotUsed verifies tool was not called", () => {
    const result = mockRun(shopAgent, "Search for unicorn saddles", {
      events: [
        MockEvent.toolCall("search_products", { query: "unicorn saddles" }),
        MockEvent.toolResult("search_products", []),
        MockEvent.done({ result: "No results found." }),
      ],
    });

    assertToolUsed(result, "search_products");
    assertToolNotUsed(result, "checkout");
    assertNoErrors(result);
  });

  it("assertToolCalledWith checks args (subset match)", () => {
    const result = mockRun(shopAgent, "Search for laptops", {
      events: [
        MockEvent.toolCall("search_products", { query: "laptops", maxResults: 3 }),
        MockEvent.toolResult("search_products", [
          { name: "MacBook Pro", price: 2499 },
        ]),
        MockEvent.done({ result: "Found laptops." }),
      ],
    });

    assertToolCalledWith(result, "search_products", { query: "laptops" });
  });
});

describe("Full Shopping Flow", () => {
  it("executes search → details → cart → checkout in order", () => {
    const result = mockRun(shopAgent, "Find a widget and buy it", {
      events: [
        MockEvent.toolCall("search_products", { query: "widget" }),
        MockEvent.toolResult("search_products", [{ id: "W-1", name: "Widget" }]),
        MockEvent.toolCall("get_product_details", { productId: "W-1" }),
        MockEvent.toolResult("get_product_details", { id: "W-1", name: "Widget", stock: 42 }),
        MockEvent.toolCall("add_to_cart", { productId: "W-1", quantity: 1 }),
        MockEvent.toolResult("add_to_cart", { success: true }),
        MockEvent.toolCall("checkout", { paymentMethod: "credit_card" }),
        MockEvent.toolResult("checkout", { orderId: "ORD-001", status: "confirmed" }),
        MockEvent.done({ result: "Order ORD-001 confirmed!" }),
      ],
    });

    // All tools were used
    assertToolUsed(result, "search_products");
    assertToolUsed(result, "get_product_details");
    assertToolUsed(result, "add_to_cart");
    assertToolUsed(result, "checkout");

    // Verify ordering with assertToolCallOrder (subsequence check)
    assertToolCallOrder(result, [
      "search_products",
      "get_product_details",
      "add_to_cart",
      "checkout",
    ]);

    // Verify exact tool set with assertToolsUsedExactly
    assertToolsUsedExactly(result, [
      "search_products",
      "get_product_details",
      "add_to_cart",
      "checkout",
    ]);
  });
});

describe("Output Validation", () => {
  it("tool result is captured in events", () => {
    const result = mockRun(shopAgent, "Place my order", {
      events: [
        MockEvent.toolCall("checkout", { paymentMethod: "credit_card" }),
        MockEvent.toolResult("checkout", {
          orderId: "ORD-12345",
          status: "confirmed",
        }),
        MockEvent.done({ result: "Order confirmed!" }),
      ],
      autoExecuteTools: false,
    });

    agentExpect(result).completed();

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

  it("output contains expected text", () => {
    const result = mockRun(shopAgent, "Search for laptops", {
      events: [
        MockEvent.toolCall("search_products", { query: "laptops" }),
        MockEvent.toolResult("search_products", [
          { name: "MacBook Pro", price: 2499 },
          { name: "ThinkPad X1", price: 1799 },
        ]),
        MockEvent.done({ result: "Found 2 laptops: MacBook Pro and ThinkPad X1." }),
      ],
    });

    agentExpect(result).completed().outputContains("MacBook");
  });
});

describe("Error in Tool Execution", () => {
  it("error event marks result as FAILED", () => {
    const result = mockRun(shopAgent, "Search for broken item", {
      events: [
        MockEvent.toolCall("search_products", { query: "broken" }),
        MockEvent.error("Database connection failed"),
      ],
    });

    assertStatus(result, "FAILED");
  });

  it("thinking + tool + done flow completes successfully", () => {
    const result = mockRun(shopAgent, "Quick search", {
      events: [
        MockEvent.thinking("Let me search for that..."),
        MockEvent.toolCall("search_products", { query: "item" }),
        MockEvent.toolResult("search_products", [{ name: "Item" }]),
        MockEvent.done({ result: "Found 1 item." }),
      ],
    });

    assertToolUsed(result, "search_products");
    assertNoErrors(result);
  });
});

describe("Max Turns Assertion", () => {
  it("verifies turn count stays within budget", () => {
    const result = mockRun(shopAgent, "Simple question", {
      events: [
        MockEvent.toolCall("search_products", { query: "item" }),
        MockEvent.toolResult("search_products", [{ name: "Item" }]),
        MockEvent.done({ result: "Found it." }),
      ],
    });

    agentExpect(result).completed().maxTurns(5);
  });
});
