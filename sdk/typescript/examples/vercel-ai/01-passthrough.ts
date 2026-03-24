/**
 * Vercel AI SDK -- Passthrough
 *
 * Demonstrates passing a Vercel AI SDK agent to runtime.run().
 * The SDK auto-detects the framework via duck-typing (.generate, .stream, .tools)
 * and uses the passthrough worker pattern.
 *
 * Path 1: Native generateText call (direct Vercel AI SDK usage).
 * Path 2: Agentspan passthrough (runtime.run wraps the agent object).
 */

import { generateText, tool } from 'ai';
import { openai } from '@ai-sdk/openai';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ── Model ────────────────────────────────────────────────
const model = openai('gpt-4o-mini');

// ── Tools ────────────────────────────────────────────────
const weatherTool = tool({
  description: 'Get current weather for a city',
  parameters: z.object({ city: z.string().describe('City name') }),
  execute: async ({ city }) => ({
    city,
    tempF: 62,
    condition: 'Foggy',
  }),
});

const tools = { weather: weatherTool };

// ── Prompt ───────────────────────────────────────────────
const prompt = 'What is the weather in San Francisco?';
const system = 'You are a helpful assistant. Use available tools to answer questions.';

// ── Path 1: Native Vercel AI SDK ─────────────────────────
async function main() {
  console.log('=== Native Vercel AI SDK ===');
  const nativeResult = await generateText({
    model,
    system,
    prompt,
    tools,
    maxSteps: 3,
  });
  console.log('Output:', nativeResult.text);
  console.log('Steps:', nativeResult.steps.length);
  console.log('Tool calls:', nativeResult.steps.flatMap(s => s.toolCalls).map(tc => tc.toolName));

  // ── Path 2: Agentspan passthrough ────────────────────────
  // Build a duck-typed agent object that agentspan detects as vercel_ai.
  // In a real integration the SDK would accept generateText options directly;
  // here we create the wrapper so detectFramework sees .generate + .stream + .tools.
  const vercelAgent = {
    id: 'weather_agent',
    tools,
    generate: async (opts: { prompt: string; onStepFinish?: (step: any) => void }) => {
      const result = await generateText({
        model,
        system,
        prompt: opts.prompt,
        tools,
        maxSteps: 3,
        onStepFinish: opts.onStepFinish,
      });
      return {
        text: result.text,
        toolCalls: result.steps.flatMap(s => s.toolCalls),
        toolResults: result.steps.flatMap(s => s.toolResults),
        finishReason: result.finishReason,
      };
    },
    stream: async function* (opts: { prompt: string }) {
      // Not used in this example but required for duck-typing detection
      yield { type: 'finish' as const };
    },
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
