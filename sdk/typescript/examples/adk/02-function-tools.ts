/**
 * Google ADK Agent with Function Tools -- tool calling via FunctionTool.
 *
 * Demonstrates:
 *   - Defining tools with FunctionTool from @google/adk
 *   - Multiple tools with typed parameters (via zod)
 *   - Tools registered as workers in Agentspan passthrough mode
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, FunctionTool } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Tool definitions ─────────────────────────────────────────────────

const getWeather = new FunctionTool({
  name: 'get_weather',
  description: 'Get the current weather for a city.',
  parameters: z.object({
    city: z.string().describe('Name of the city to get weather for'),
  }),
  execute: async (args: { city: string }) => {
    const weatherData: Record<string, { temp_c: number; condition: string; humidity: number }> = {
      tokyo: { temp_c: 22, condition: 'Clear', humidity: 65 },
      paris: { temp_c: 18, condition: 'Partly Cloudy', humidity: 72 },
      sydney: { temp_c: 25, condition: 'Sunny', humidity: 58 },
      mumbai: { temp_c: 32, condition: 'Humid', humidity: 85 },
    };
    const data = weatherData[args.city.toLowerCase()] ?? { temp_c: 20, condition: 'Unknown', humidity: 50 };
    return { city: args.city, ...data };
  },
});

const convertTemperature = new FunctionTool({
  name: 'convert_temperature',
  description: 'Convert temperature between Celsius and Fahrenheit.',
  parameters: z.object({
    temp_celsius: z.number().describe('Temperature in Celsius'),
    to_unit: z.string().describe('Target unit: "fahrenheit" or "kelvin"').default('fahrenheit'),
  }),
  execute: async (args: { temp_celsius: number; to_unit?: string }) => {
    const unit = (args.to_unit ?? 'fahrenheit').toLowerCase();
    if (unit === 'fahrenheit') {
      const converted = args.temp_celsius * 9 / 5 + 32;
      return { celsius: args.temp_celsius, fahrenheit: Math.round(converted * 10) / 10 };
    } else if (unit === 'kelvin') {
      const converted = args.temp_celsius + 273.15;
      return { celsius: args.temp_celsius, kelvin: Math.round(converted * 10) / 10 };
    }
    return { error: `Unknown unit: ${args.to_unit}` };
  },
});

const getTimeZone = new FunctionTool({
  name: 'get_time_zone',
  description: 'Get the timezone for a city.',
  parameters: z.object({
    city: z.string().describe('Name of the city'),
  }),
  execute: async (args: { city: string }) => {
    const timezones: Record<string, { timezone: string; utc_offset: string }> = {
      tokyo: { timezone: 'JST', utc_offset: '+9:00' },
      paris: { timezone: 'CET', utc_offset: '+1:00' },
      sydney: { timezone: 'AEST', utc_offset: '+10:00' },
      mumbai: { timezone: 'IST', utc_offset: '+5:30' },
    };
    return timezones[args.city.toLowerCase()] ?? { timezone: 'Unknown', utc_offset: 'Unknown' };
  },
});

// ── Agent ────────────────────────────────────────────────────────────

export const agent = new LlmAgent({
  name: 'travel_assistant',
  model,
  instruction:
    'You are a travel assistant. Help users with weather information, ' +
    'temperature conversions, and timezone lookups. Be concise and accurate.',
  tools: [getWeather, convertTemperature, getTimeZone],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    agent,
    "What's the weather in Tokyo right now? Convert the temperature to " +
    "Fahrenheit and tell me what timezone they're in.",
    );
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/adk --agents travel_assistant
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
