'use strict';

/**
 * Weather Streaming Example
 *
 * Same as weather.js but uses runtime.stream() to print events as they arrive.
 *
 * Run:
 *   node examples/weather-stream.js
 *   node examples/weather-stream.js "What's the weather in Miami?"
 */

require('dotenv').config();

const { Agent, AgentRuntime, tool } = require('../src/index');

const WEATHER_DATA = {
  'new york':     { temp: 72, condition: 'Partly Cloudy' },
  'san francisco': { temp: 58, condition: 'Foggy' },
  'miami':        { temp: 85, condition: 'Sunny' },
};

const getWeather = tool(
  async function getWeather({ city }) {
    const data = WEATHER_DATA[city.toLowerCase()] || { temp: 70, condition: 'Clear' };
    return { city, temperature_f: data.temp, condition: data.condition };
  },
  {
    description: 'Get the current weather for a city.',
    inputSchema: {
      type: 'object',
      properties: {
        city: { type: 'string', description: 'City name' },
      },
      required: ['city'],
    },
  }
);

const agent = new Agent({
  name: 'weather_stream_agent',
  model: process.env.AGENT_LLM_MODEL || 'openai/gpt-4o',
  instructions: 'You are a helpful weather assistant.',
  tools: [getWeather],
});

async function main() {
  const prompt = process.argv[2] || "What's the weather in New York and Miami?";
  console.log(`\nPrompt: ${prompt}\n`);

  const runtime = new AgentRuntime({
    serverUrl: process.env.AGENTSPAN_SERVER_URL || 'http://localhost:8080',
  });

  try {
    for await (const event of runtime.stream(agent, prompt)) {
      switch (event.type) {
        case 'thinking':
          console.log(`  [thinking] ${event.content}`);
          break;
        case 'tool_call':
          console.log(`  [tool_call] ${event.toolName}(${JSON.stringify(event.args)})`);
          break;
        case 'tool_result':
          console.log(`  [tool_result] ${event.toolName} → ${JSON.stringify(event.result)}`);
          break;
        case 'waiting':
          console.log('  [waiting] Human approval required');
          break;
        case 'error':
          console.error(`  [error] ${event.error}`);
          break;
        case 'done':
          console.log(`\nResult: ${JSON.stringify(event.output, null, 2)}`);
          break;
      }
    }
  } finally {
    await runtime.shutdown();
  }
}

main().catch((err) => {
  console.error('Error:', err.message || err);
  process.exit(1);
});
