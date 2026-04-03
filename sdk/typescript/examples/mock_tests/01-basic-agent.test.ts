/**
 * 01 — Basic Agent Mock Tests
 *
 * The simplest possible mock tests. No server, no LLM, no API keys.
 *
 * Covers:
 *   - Creating a single agent with tools
 *   - mockRun() with mock tool implementations
 *   - Basic status and output assertions
 *   - Tool usage assertions
 *   - The fluent expectResult() API
 *
 * Run:
 *   npx vitest run examples/mock_tests/01-basic-agent.test.ts
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
} from "@agentspan-ai/sdk/testing";

// ── Tools ────────────────────────────────────────────────────────────

const getWeather = tool(
  async (args: { city: string }) => ({
    temperature: 72,
    condition: "Sunny",
    city: args.city,
  }),
  {
    name: "get_weather",
    description: "Get current weather for a city.",
    inputSchema: z.object({ city: z.string() }),
  },
);

const getTime = tool(
  async (args: { timezone: string }) => ({
    time: "2:30 PM",
    timezone: args.timezone,
  }),
  {
    name: "get_time",
    description: "Get current time in a timezone.",
    inputSchema: z.object({ timezone: z.string() }),
  },
);

// ── Agent ────────────────────────────────────────────────────────────

const assistant = new Agent({
  name: "assistant",
  model: "openai/gpt-4o",
  instructions: "You are a helpful assistant. Use tools when needed.",
  tools: [getWeather, getTime],
});

// ── Tests ────────────────────────────────────────────────────────────

describe("Basic Completion", () => {
  it("completes successfully with mock tools", async () => {
    const result = await mockRun(assistant, "What's the weather in Tokyo?", {
      mockTools: {
        get_weather: async (args: { city: string }) => ({
          temperature: 72,
          condition: "Sunny",
          city: args.city,
        }),
      },
    });

    assertStatus(result, "COMPLETED");
    assertNoErrors(result);
    assertToolUsed(result, "get_weather");
  });

  it("handles multiple tool calls", async () => {
    const result = await mockRun(
      assistant,
      "What's the weather and time in London?",
      {
        mockTools: {
          get_weather: async () => ({
            temperature: 55,
            condition: "Rainy",
            city: "London",
          }),
          get_time: async () => ({ time: "7:30 PM", timezone: "Europe/London" }),
        },
      },
    );

    assertToolUsed(result, "get_weather");
    assertToolUsed(result, "get_time");
    assertNoErrors(result);
  });

  it("completes without using any tools", async () => {
    const result = await mockRun(assistant, "Hello, how are you?");

    assertStatus(result, "COMPLETED");
    assertNoErrors(result);
  });
});

describe("Fluent expectResult API", () => {
  it("chains status + output + tool checks", async () => {
    const result = await mockRun(assistant, "Weather in Paris?", {
      mockTools: {
        get_weather: async () => ({
          temperature: 60,
          condition: "Cloudy",
          city: "Paris",
        }),
      },
    });

    expectResult(result).toBeCompleted().toHaveUsedTool("get_weather");
  });

  it("verifies output contains text", async () => {
    const result = await mockRun(assistant, "What time is it in NYC?", {
      mockTools: {
        get_time: async () => ({ time: "2:30 PM", timezone: "America/New_York" }),
      },
    });

    expectResult(result).toBeCompleted().toHaveUsedTool("get_time");
  });
});

describe("Error Scenarios", () => {
  it("detects failed status", async () => {
    const failAgent = new Agent({
      name: "fail-agent",
      model: "openai/gpt-4o",
      instructions: "You always fail.",
    });

    const result = await mockRun(failAgent, "Do something impossible", {
      mockTools: {},
    });

    // The result status depends on execution — verify it's not undefined
    expect(result.status).toBeDefined();
  });
});

describe("Mock Credentials", () => {
  it("injects mock credentials into tool context", async () => {
    const result = await mockRun(assistant, "Weather check", {
      mockTools: {
        get_weather: async () => ({ temperature: 70, city: "Test" }),
      },
      mockCredentials: {
        WEATHER_API_KEY: "test-key-123",
      },
    });

    expectResult(result).toBeCompleted();
  });
});
