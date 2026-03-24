/**
 * Vercel AI SDK Tools + Native Agent -- Structured Output
 *
 * Demonstrates typed structured output using a Zod schema as the Agent's outputType.
 * The agentspan runtime sends the schema to the server, which constrains the LLM
 * to produce valid JSON matching the schema.
 */

import { z } from 'zod';
import { Agent, AgentRuntime } from '../../src/index.js';

// ── Schema ───────────────────────────────────────────────
const PersonSchema = z.object({
  name: z.string().describe('Full name'),
  age: z.number().int().describe('Age in years'),
  occupation: z.string().describe('Current job title'),
  skills: z.array(z.string()).describe('Top 3 skills'),
});

type Person = z.infer<typeof PersonSchema>;

// ── Native Agent with structured output ──────────────────
const agent = new Agent({
  name: 'structured_output_agent',
  model: 'openai/gpt-4o-mini',
  instructions: 'Generate fictional but realistic profiles when asked.',
  outputType: PersonSchema, // Zod schema auto-converted to JSON Schema
});

const prompt = 'Generate a profile for a fictional ML engineer from Japan.';

// ── Run on agentspan ─────────────────────────────────────
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, prompt);
    console.log('Status:', result.status);

    // Output conforms to the schema
    const person = result.output as unknown as Person;
    console.log('Name:', person.name);
    console.log('Age:', person.age);
    console.log('Occupation:', person.occupation);
    console.log('Skills:', person.skills);

    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
