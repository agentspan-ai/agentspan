/**
 * 01 — Basic Agent Mock Tests
 *
 * The simplest possible mock tests. No server, no LLM, no API keys.
 *
 * Covers:
 *   - Creating a single agent with tools
 *   - MockEvent factory + mockRun with scripted events
 *   - Basic status and output assertions
 *   - Tool usage assertions
 *   - The fluent expect() API
 *
 * Run:
 *   npx vitest run examples/mock_tests/01-basic-agent.test.ts
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
  it("completes successfully with scripted tool events", () => {
    const result = mockRun(assistant, "What's the weather in Tokyo?", {
      events: [
        MockEvent.toolCall("get_weather", { city: "Tokyo" }),
        MockEvent.toolResult("get_weather", {
          temperature: 72,
          condition: "Sunny",
          city: "Tokyo",
        }),
        MockEvent.done({ result: "It's 72°F and Sunny in Tokyo." }),
      ],
    });

    assertStatus(result, "COMPLETED");
    assertNoErrors(result);
    assertToolUsed(result, "get_weather");
  });

  it("handles multiple tool calls", () => {
    const result = mockRun(
      assistant,
      "What's the weather and time in London?",
      {
        events: [
          MockEvent.toolCall("get_weather", { city: "London" }),
          MockEvent.toolResult("get_weather", {
            temperature: 55,
            condition: "Rainy",
            city: "London",
          }),
          MockEvent.toolCall("get_time", { timezone: "Europe/London" }),
          MockEvent.toolResult("get_time", {
            time: "7:30 PM",
            timezone: "Europe/London",
          }),
          MockEvent.done({ result: "London: 55°F Rainy, 7:30 PM" }),
        ],
      },
    );

    assertToolUsed(result, "get_weather");
    assertToolUsed(result, "get_time");
    assertNoErrors(result);
  });

  it("completes without using any tools", () => {
    const result = mockRun(assistant, "Hello, how are you?", {
      events: [MockEvent.done("Hello! I'm doing great.")],
    });

    assertStatus(result, "COMPLETED");
    assertNoErrors(result);
  });
});

describe("Fluent expect API", () => {
  it("chains status + tool checks", () => {
    const result = mockRun(assistant, "Weather in Paris?", {
      events: [
        MockEvent.toolCall("get_weather", { city: "Paris" }),
        MockEvent.toolResult("get_weather", {
          temperature: 60,
          condition: "Cloudy",
          city: "Paris",
        }),
        MockEvent.done({ result: "It's 60°F and Cloudy in Paris." }),
      ],
    });

    agentExpect(result).completed().usedTool("get_weather");
  });

  it("verifies output contains text", () => {
    const result = mockRun(assistant, "What time is it in NYC?", {
      events: [
        MockEvent.toolCall("get_time", { timezone: "America/New_York" }),
        MockEvent.toolResult("get_time", {
          time: "2:30 PM",
          timezone: "America/New_York",
        }),
        MockEvent.done({ result: "It's 2:30 PM in NYC." }),
      ],
    });

    agentExpect(result).completed().usedTool("get_time").outputContains("2:30 PM");
  });
});

describe("Error Scenarios", () => {
  it("detects failed status via error event", () => {
    const failAgent = new Agent({
      name: "fail-agent",
      model: "openai/gpt-4o",
      instructions: "You always fail.",
    });

    const result = mockRun(failAgent, "Do something impossible", {
      events: [MockEvent.error("Cannot process request")],
    });

    assertStatus(result, "FAILED");
  });
});

describe("Auto-Execute Tools", () => {
  it("auto-executes tool functions when available", () => {
    const result = mockRun(assistant, "Weather check", {
      events: [
        MockEvent.toolCall("get_weather", { city: "Test" }),
        MockEvent.done({ result: "Weather checked." }),
      ],
      // autoExecuteTools defaults to true — tool func will run
    });

    assertToolUsed(result, "get_weather");
    agentExpect(result).completed();
  });
});
