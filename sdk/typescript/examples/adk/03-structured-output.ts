/**
 * Google ADK Agent with Structured Output -- enforced JSON schema response.
 *
 * Demonstrates:
 *   - Using outputSchema (Zod) for structured, validated responses
 *   - Generation config for controlling model behavior
 *   - The server normalizer maps ADK's outputSchema to AgentConfig.outputType
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Output schemas ───────────────────────────────────────────────────

const IngredientSchema = z.object({
  name: z.string(),
  quantity: z.string(),
  unit: z.string(),
});

const RecipeStepSchema = z.object({
  step_number: z.number(),
  instruction: z.string(),
  duration_minutes: z.number(),
});

const RecipeSchema = z.object({
  name: z.string(),
  servings: z.number(),
  prep_time_minutes: z.number(),
  cook_time_minutes: z.number(),
  ingredients: z.array(IngredientSchema),
  steps: z.array(RecipeStepSchema),
  difficulty: z.string(),
});

// ── Agent ────────────────────────────────────────────────────────────

export const agent = new LlmAgent({
  name: 'recipe_generator',
  model,
  instruction:
    'You are a professional chef assistant. When asked for a recipe, ' +
    'provide a complete, well-structured recipe with precise measurements, ' +
    'clear step-by-step instructions, and accurate timing.',
  outputSchema: RecipeSchema,
  generateContentConfig: {
    temperature: 0.3,
  },
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    agent,
    'Give me a recipe for classic Italian carbonara pasta.',
    );
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/adk --agents recipe_generator
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('03-structured-output.ts') || process.argv[1]?.endsWith('03-structured-output.js')) {
  main().catch(console.error);
}
