/**
 * Vercel AI SDK -- Streaming
 *
 * Demonstrates streaming tokens from a Vercel AI SDK agent.
 *
 * Path 1: Native streamText call with real-time token output.
 * Path 2: Agentspan passthrough (agent.generate runs internally;
 *          streaming is simulated via the duck-typed wrapper).
 */

import { streamText, generateText, tool } from 'ai';
import { openai } from '@ai-sdk/openai';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ── Model ────────────────────────────────────────────────
const model = openai('gpt-4o-mini');

// ── Tools ────────────────────────────────────────────────
const weatherTool = tool({
  description: 'Get current weather for a city',
  parameters: z.object({ city: z.string() }),
  execute: async ({ city }) => ({
    city,
    tempF: 62,
    condition: 'Foggy',
  }),
});

const tools = { weather: weatherTool };
const prompt = 'Explain quantum computing in one paragraph, then tell me the weather in San Francisco.';
const system = 'You are a helpful assistant. Use tools when relevant.';

// ── Path 1: Native Vercel AI SDK streaming ───────────────
async function main() {
  console.log('=== Native Vercel AI SDK (streaming) ===');
  const streamResult = streamText({
    model,
    system,
    prompt,
    tools,
    maxSteps: 3,
  });

  // Stream text tokens as they arrive
  process.stdout.write('Output: ');
  for await (const chunk of streamResult.textStream) {
    process.stdout.write(chunk);
  }
  console.log('\n');

  // After the stream completes, access full result (properties are promises)
  const finishReason = await streamResult.finishReason;
  const steps = await streamResult.steps;
  console.log('Finish reason:', finishReason);
  console.log('Steps:', steps.length);
  console.log(
    'Tool calls:',
    steps.flatMap(s => s.toolCalls).map(tc => tc.toolName),
  );

  // ── Path 2: Agentspan passthrough ────────────────────────
  const vercelAgent = {
    id: 'streaming_agent',
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
      // Real streaming via streamText for the duck-typed wrapper
      const result = streamText({
        model,
        system,
        prompt: opts.prompt,
        tools,
        maxSteps: 3,
      });
      for await (const chunk of result.textStream) {
        yield { type: 'text-delta' as const, textDelta: chunk };
      }
      yield { type: 'finish' as const, finishReason: 'stop' as const };
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
