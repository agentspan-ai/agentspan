/**
 * Vercel AI SDK -- Structured Output
 *
 * Demonstrates generating typed structured output using:
 * - generateObject() for direct schema-based generation
 * - generateText() with experimental_output: Output.object() for tool-augmented structured output
 *
 * Path 1: Native generateObject call (direct Vercel AI SDK usage).
 * Path 2: Agentspan passthrough with structured output.
 */

import { generateObject, generateText, Output } from 'ai';
import { openai } from '@ai-sdk/openai';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ── Model ────────────────────────────────────────────────
const model = openai('gpt-4o-mini');

// ── Schema ───────────────────────────────────────────────
const PersonSchema = z.object({
  name: z.string().describe('Full name'),
  age: z.number().int().describe('Age in years'),
  occupation: z.string().describe('Current job title'),
  skills: z.array(z.string()).describe('Top 3 skills'),
});

type Person = z.infer<typeof PersonSchema>;

const prompt = 'Generate a profile for a fictional ML engineer from Japan.';

// ── Path 1a: Native generateObject ───────────────────────
async function main() {
  console.log('=== Native generateObject ===');
  const objectResult = await generateObject({
    model,
    schema: PersonSchema,
    prompt,
  });
  console.log('Output:', JSON.stringify(objectResult.object, null, 2));
  console.log('Usage:', objectResult.usage);

  // ── Path 1b: Native generateText with Output.object ──────
  console.log('\n=== Native generateText + Output.object ===');
  const textResult = await generateText({
    model,
    prompt,
    experimental_output: Output.object({ schema: PersonSchema }),
  });
  console.log('Output:', JSON.stringify(textResult.experimental_output, null, 2));
  console.log('Steps:', textResult.steps.length);

  // ── Path 2: Agentspan passthrough ────────────────────────
  const vercelAgent = {
    id: 'structured_output_agent',
    tools: {},
    generate: async (opts: { prompt: string; onStepFinish?: (step: any) => void }) => {
      const result = await generateObject({
        model,
        schema: PersonSchema,
        prompt: opts.prompt,
      });
      const validated: Person = PersonSchema.parse(result.object);
      return {
        text: JSON.stringify(validated, null, 2),
        toolCalls: [],
        toolResults: [],
        finishReason: 'stop' as const,
        experimental_output: validated,
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
