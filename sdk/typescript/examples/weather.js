'use strict';

/**
 * Weather Example — mirrors Python sdk/python/examples/02_tools.py
 *
 * Demonstrates:
 *   - Defining tools with tool()
 *   - Creating an agent
 *   - Running with AgentRuntime
 *
 * Requirements:
 *   - Conductor server running at http://localhost:8080
 *   - AGENTSPAN_SERVER_URL env var (default: http://localhost:8080/api)
 *   - AGENT_LLM_MODEL env var, e.g. openai/gpt-4o
 *
 * Run:
 *   node examples/weather.js
 *   node examples/weather.js "What's the weather in Tokyo?"
 */

require('dotenv').config();

const { Agent, AgentRuntime, tool } = require('../src/index');

// ── Tool definitions ──────────────────────────────────────────────────────

const WEATHER_DATA = {
  'new york':     { temp: 72, condition: 'Partly Cloudy' },
  'san francisco': { temp: 58, condition: 'Foggy' },
  'miami':        { temp: 85, condition: 'Sunny' },
  'london':       { temp: 55, condition: 'Overcast' },
  'tokyo':        { temp: 68, condition: 'Clear' },
};

const getWeather = tool(
  async function getWeather({ city }) {
    const data = WEATHER_DATA[city.toLowerCase()] || { temp: 70, condition: 'Clear' };
    return {
      city,
      temperature_f: data.temp,
      condition: data.condition,
    };
  },
  {
    description: 'Get the current weather for a city.',
    inputSchema: {
      type: 'object',
      properties: {
        city: { type: 'string', description: 'The city to get weather for' },
      },
      required: ['city'],
    },
  }
);

const calculate = tool(
  async function calculate({ expression }) {
    try {
      // eslint-disable-next-line no-eval
      const result = eval(expression);
      return { expression, result };
    } catch (err) {
      return { expression, error: err.message };
    }
  },
  {
    description: 'Evaluate a math expression, e.g. "2 + 2" or "Math.sqrt(16)".',
    inputSchema: {
      type: 'object',
      properties: {
        expression: { type: 'string', description: 'Math expression to evaluate' },
      },
      required: ['expression'],
    },
  }
);

// ── Agent ─────────────────────────────────────────────────────────────────

const agent = new Agent({
  name: 'weather_agent',
  model: process.env.AGENT_LLM_MODEL || 'openai/gpt-4o',
  instructions: 'You are a helpful weather assistant. Use the provided tools to answer weather and math questions.',
  tools: [getWeather, calculate],
});

// ── Run ───────────────────────────────────────────────────────────────────

async function main() {
  const prompt = process.argv[2] || "What's the weather in San Francisco? Also, what is 15 * 4?";
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

main().catch((err) => {
  console.error('Error:', err.message || err);
  process.exit(1);
});
