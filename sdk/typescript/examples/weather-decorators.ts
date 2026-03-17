/**
 * Weather Example — TypeScript @AgentTool decorator style
 *
 * Same agent as weather.js but tools are defined as class methods
 * decorated with @AgentTool.
 *
 * Run:
 *   npx ts-node --project decorators/tsconfig.json examples/weather-decorators.ts
 */

import * as dotenv from 'dotenv';
dotenv.config();

// Plain JS SDK (no TS build needed for the core)
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { Agent, AgentRuntime } = require('../src/index');

// TypeScript decorator module
import { AgentTool, toolsFrom } from '../decorators/index';

// ── Tool class ────────────────────────────────────────────────────────────

const WEATHER_DATA: Record<string, { temp: number; condition: string }> = {
  'new york':      { temp: 72, condition: 'Partly Cloudy' },
  'san francisco': { temp: 58, condition: 'Foggy' },
  'miami':         { temp: 85, condition: 'Sunny' },
  'london':        { temp: 55, condition: 'Overcast' },
  'tokyo':         { temp: 68, condition: 'Clear' },
};

class WeatherTools {
  @AgentTool({
    description: 'Get the current weather for a city.',
    inputSchema: {
      type: 'object',
      properties: {
        city: { type: 'string', description: 'The city to get weather for' },
      },
      required: ['city'],
    },
  })
  async getWeather({ city }: { city: string }) {
    const data = WEATHER_DATA[city.toLowerCase()] || { temp: 70, condition: 'Clear' };
    return { city, temperature_f: data.temp, condition: data.condition };
  }

  @AgentTool({
    description: 'Evaluate a math expression.',
    inputSchema: {
      type: 'object',
      properties: {
        expression: { type: 'string', description: 'Math expression to evaluate' },
      },
      required: ['expression'],
    },
  })
  async calculate({ expression }: { expression: string }) {
    try {
      // eslint-disable-next-line no-eval
      const result = eval(expression) as number;
      return { expression, result };
    } catch (err) {
      return { expression, error: String(err) };
    }
  }
}

// ── Agent ─────────────────────────────────────────────────────────────────

const tools = toolsFrom(new WeatherTools());

const agent = new Agent({
  name: 'weather_decorator_agent',
  model: process.env.AGENT_LLM_MODEL || 'openai/gpt-4o',
  instructions: 'You are a helpful weather assistant.',
  tools,
});

// ── Run ───────────────────────────────────────────────────────────────────

async function main() {
  const prompt = process.argv[2] || "What's the weather in San Francisco?";
  console.log(`\nPrompt: ${prompt}\n`);

  const runtime = new AgentRuntime({
    serverUrl: process.env.AGENTSPAN_SERVER_URL || 'http://localhost:8080',
  });

  try {
    const result = await runtime.run(agent, prompt);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch((err: Error) => {
  console.error('Error:', err.message || err);
  process.exit(1);
});
