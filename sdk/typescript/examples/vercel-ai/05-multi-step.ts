/**
 * Vercel AI SDK -- Multi-Step Agent Loop
 *
 * Demonstrates a multi-step agent loop where the agent calls tools
 * iteratively until it has enough information to produce a final answer.
 *
 * In production you would use:
 *   import { generateText } from 'ai';
 *   const result = await generateText({ model, tools, maxSteps: 5, prompt });
 */

import { AgentRuntime } from '../../src/index.js';

// -- Tool definitions --
function lookupWeather(city: string): string {
  const data: Record<string, string> = {
    'san francisco': '62F, Foggy',
    'new york': '45F, Cloudy',
    'tokyo': '58F, Clear',
    'london': '50F, Rainy',
  };
  return data[city.toLowerCase()] ?? `Weather data not available for ${city}`;
}

function lookupTime(city: string): string {
  const offsets: Record<string, number> = {
    'san francisco': -8,
    'new york': -5,
    'tokyo': 9,
    'london': 0,
  };
  const offset = offsets[city.toLowerCase()];
  if (offset === undefined) return `Time zone not available for ${city}`;
  const now = new Date();
  const utc = now.getTime() + now.getTimezoneOffset() * 60000;
  const local = new Date(utc + 3600000 * offset);
  return `${local.getHours()}:${String(local.getMinutes()).padStart(2, '0')} local time (UTC${offset >= 0 ? '+' : ''}${offset})`;
}

// -- Mock Vercel AI SDK agent with multi-step tool loop --
// Detection requires: .generate() + .stream() + .tools
const vercelAgent = {
  generate: async (options: { prompt: string; onStepFinish?: Function }) => {
    const prompt = options.prompt.toLowerCase();
    const steps: { tool: string; input: string; output: string }[] = [];

    // Step 1: Look up weather for each city mentioned
    const cities = ['San Francisco', 'Tokyo'];
    for (const city of cities) {
      if (prompt.includes(city.toLowerCase())) {
        steps.push({
          tool: 'lookupWeather',
          input: city,
          output: lookupWeather(city),
        });
        steps.push({
          tool: 'lookupTime',
          input: city,
          output: lookupTime(city),
        });
      }
    }

    // If no specific cities found, use defaults
    if (steps.length === 0) {
      for (const city of cities) {
        steps.push({
          tool: 'lookupWeather',
          input: city,
          output: lookupWeather(city),
        });
        steps.push({
          tool: 'lookupTime',
          input: city,
          output: lookupTime(city),
        });
      }
    }

    // Final step: generate answer
    const summaryParts = [];
    for (let i = 0; i < steps.length; i += 2) {
      summaryParts.push(
        `${steps[i].input}: ${steps[i].output}, ${steps[i + 1]?.output ?? ''}`,
      );
    }

    return {
      text: `Here is the current weather and time:\n\n${summaryParts.join('\n')}`,
      toolCalls: steps.map((s) => ({
        toolName: s.tool,
        args: { city: s.input },
      })),
      toolResults: steps.map((s) => ({
        toolName: s.tool,
        result: s.output,
      })),
      finishReason: 'stop' as const,
      steps: steps.length,
    };
  },

  stream: async function* () { yield { type: 'finish' }; },
  tools: [
    { name: 'lookupWeather', description: 'Look up weather for a city' },
    { name: 'lookupTime', description: 'Look up local time for a city' },
  ],
  id: 'vercel_multistep_agent',
};

async function main() {
  const runtime = new AgentRuntime();

  console.log('Running multi-step Vercel AI agent...\n');
  const result = await runtime.run(
    vercelAgent,
    'What is the current weather and time in San Francisco and Tokyo?',
  );
  console.log('Status:', result.status);
  result.printResult();

  await runtime.shutdown();
}

main().catch(console.error);
