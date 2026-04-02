// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

/**
 * OpenAI Agent with Function Tools -- tool calling via the `tool()` helper.
 *
 * Demonstrates:
 *   - Defining function tools with zod schemas
 *   - Multiple tools with typed parameters
 *   - Running via Agentspan passthrough
 *
 * Requirements:
 *   - AGENTSPAN_SERVER_URL for the Agentspan path
 */

import { Agent, tool, setTracingDisabled } from '@openai/agents';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

setTracingDisabled(true);

// ── Tools ───────────────────────────────────────────────────────────

const getWeather = tool({
  name: 'get_weather',
  description: 'Get the current weather for a city.',
  parameters: z.object({ city: z.string().describe('City name') }),
  execute: async ({ city }) => {
    const weatherData: Record<string, string> = {
      'new york': '72F, Partly Cloudy',
      'san francisco': '58F, Foggy',
      miami: '85F, Sunny',
      london: '55F, Rainy',
    };
    return weatherData[city.toLowerCase()] ?? `Weather data not available for ${city}`;
  },
});

const calculate = tool({
  name: 'calculate',
  description: 'Evaluate a mathematical expression and return the result.',
  parameters: z.object({ expression: z.string().describe('Math expression to evaluate') }),
  execute: async ({ expression }) => {
    try {
      // Simple safe eval for basic math
      const sanitized = expression.replace(/[^0-9+\-*/().sqrt,pow ]/g, '');
      const result = Function(`"use strict"; return (${sanitized})`)();
      return String(result);
    } catch (e: any) {
      return `Error: ${e.message}`;
    }
  },
});

const lookupPopulation = tool({
  name: 'lookup_population',
  description: 'Look up the population of a city.',
  parameters: z.object({ city: z.string().describe('City name') }),
  execute: async ({ city }) => {
    const populations: Record<string, string> = {
      'new york': '8.3 million',
      'san francisco': '874,000',
      miami: '442,000',
      london: '8.8 million',
    };
    return populations[city.toLowerCase()] ?? 'Unknown';
  },
});

// ── Agent ───────────────────────────────────────────────────────────

export const agent = new Agent({
  name: 'multi_tool_agent',
  instructions:
    'You are a helpful assistant with access to weather, calculator, ' +
    'and population lookup tools. Use them to answer questions accurately.',
  model: 'gpt-4o-mini',
  tools: [getWeather, calculate, lookupPopulation],
});

const prompt =
  "What's the weather in San Francisco? Also, what's the population there " +
  "and what's the square root of that number (just the digits)?";

// ── Run on agentspan ──────────────────────────────────────────────
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, prompt);
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/openai --agents multi_tool_agent
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('02-function-tools.ts') || process.argv[1]?.endsWith('02-function-tools.js')) {
  main().catch(console.error);
}
