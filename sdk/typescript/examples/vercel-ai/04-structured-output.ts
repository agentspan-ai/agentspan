/**
 * Vercel AI SDK -- Structured Output
 *
 * Demonstrates using Zod schemas to produce structured (typed) output
 * from a Vercel AI SDK agent running on Agentspan.
 *
 * In production you would use:
 *   import { generateObject } from 'ai';
 *   import { z } from 'zod';
 *   const result = await generateObject({ model, schema, prompt });
 */

import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// -- Define the output schema --
const PersonSchema = z.object({
  name: z.string().describe('Full name'),
  age: z.number().int().describe('Age in years'),
  occupation: z.string().describe('Current job title'),
  skills: z.array(z.string()).describe('Top 3 skills'),
});

type Person = z.infer<typeof PersonSchema>;

// -- Mock Vercel AI SDK agent with structured output --
// Detection requires: .generate() + .stream() + .tools
const vercelAgent = {
  generate: async (options: { prompt: string; onStepFinish?: Function }) => {
    // Simulate structured output generation
    const person: Person = {
      name: 'Aiko Yamamoto',
      age: 31,
      occupation: 'Machine Learning Engineer',
      skills: ['PyTorch', 'Distributed Systems', 'Natural Language Processing'],
    };

    // Validate against schema
    const validated = PersonSchema.parse(person);

    return {
      text: JSON.stringify(validated, null, 2),
      toolCalls: [],
      finishReason: 'stop' as const,
      experimental_output: validated,
    };
  },

  stream: async function* () { yield { type: 'finish' }; },
  tools: [],
  id: 'vercel_structured_output_agent',
};

async function main() {
  const runtime = new AgentRuntime();

  console.log('Running Vercel AI structured output agent...\n');
  const result = await runtime.run(
    vercelAgent,
    'Generate a profile for a fictional ML engineer from Japan.',
  );
  console.log('Status:', result.status);
  result.printResult();

  await runtime.shutdown();
}

main().catch(console.error);
