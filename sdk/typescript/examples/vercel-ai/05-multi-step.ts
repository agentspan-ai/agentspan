/**
 * Vercel AI SDK -- Multi-Step Agent Loop
 *
 * Demonstrates a multi-step agent loop where generateText is called with
 * maxSteps > 1. The model calls tools iteratively until it has enough
 * information to produce a final answer.
 *
 * Path 1: Native generateText with maxSteps and onStepFinish callback.
 * Path 2: Agentspan passthrough with the same multi-step behavior.
 */

import { generateText, tool } from 'ai';
import { openai } from '@ai-sdk/openai';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ── Model ────────────────────────────────────────────────
const model = openai('gpt-4o-mini');

// ── Tool definitions ─────────────────────────────────────
const weatherData: Record<string, string> = {
  'san francisco': '62F, Foggy',
  'new york': '45F, Cloudy',
  'tokyo': '58F, Clear',
  'london': '50F, Rainy',
};

const timeData: Record<string, string> = {
  'san francisco': '09:30 PST (UTC-8)',
  'new york': '12:30 EST (UTC-5)',
  'tokyo': '02:30 JST (UTC+9)',
  'london': '17:30 GMT (UTC+0)',
};

const lookupWeather = tool({
  description: 'Look up current weather for a city.',
  parameters: z.object({ city: z.string().describe('City name') }),
  execute: async ({ city }) => {
    const data = weatherData[city.toLowerCase()];
    return data ?? `Weather data not available for ${city}`;
  },
});

const lookupTime = tool({
  description: 'Look up current local time for a city.',
  parameters: z.object({ city: z.string().describe('City name') }),
  execute: async ({ city }) => {
    const data = timeData[city.toLowerCase()];
    return data ?? `Time data not available for ${city}`;
  },
});

const tools = { lookupWeather, lookupTime };
const prompt = 'What is the current weather and time in San Francisco and Tokyo?';
const system = 'You are a helpful assistant. Use the available tools to look up weather and time data, then summarize the results.';

// ── Path 1: Native Vercel AI SDK (multi-step) ────────────
async function main() {
  console.log('=== Native Vercel AI SDK (multi-step) ===');
  let stepCount = 0;
  const nativeResult = await generateText({
    model,
    system,
    prompt,
    tools,
    maxSteps: 8,
    onStepFinish: (step) => {
      stepCount++;
      const toolNames = step.toolCalls.map(tc => tc.toolName);
      console.log(`  Step ${stepCount}: finish=${step.finishReason}, tools=[${toolNames.join(', ')}]`);
    },
  });
  console.log('Output:', nativeResult.text);
  console.log('Total steps:', nativeResult.steps.length);
  console.log(
    'All tool calls:',
    nativeResult.steps.flatMap(s => s.toolCalls).map(tc => `${tc.toolName}(${JSON.stringify(tc.args)})`),
  );

  // ── Path 2: Agentspan passthrough ────────────────────────
  const vercelAgent = {
    id: 'multistep_agent',
    tools,
    generate: async (opts: { prompt: string; onStepFinish?: (step: any) => void }) => {
      const result = await generateText({
        model,
        system,
        prompt: opts.prompt,
        tools,
        maxSteps: 8,
        onStepFinish: opts.onStepFinish,
      });
      return {
        text: result.text,
        toolCalls: result.steps.flatMap(s => s.toolCalls),
        toolResults: result.steps.flatMap(s => s.toolResults),
        finishReason: result.finishReason,
        steps: result.steps.length,
      };
    },
    stream: async function* () { yield { type: 'finish' as const }; },
  };

  console.log('\n=== Agentspan Passthrough ===');
  const runtime = new AgentRuntime();
  try {
    const agentspanResult = await runtime.run(vercelAgent, prompt);
    console.log('Output:', JSON.stringify(agentspanResult.output));
    console.log('Status:', agentspanResult.status);
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
