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
 *   - GOOGLE_API_KEY or GOOGLE_GENAI_API_KEY for native path
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, InMemoryRunner, InMemorySessionService } from '@google/adk';
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

const agent = new LlmAgent({
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

// ── Path 1: Native ADK ──────────────────────────────────────────────

async function runNative() {
  console.log('=== Native ADK ===');
  const sessionService = new InMemorySessionService();
  const runner = new InMemoryRunner({ agent, appName: 'structured-output', sessionService });
  const session = await sessionService.createSession({ appName: 'structured-output', userId: 'user1' });

  const message = { role: 'user' as const, parts: [{ text: 'Give me a recipe for classic Italian carbonara pasta.' }] };

  try {
    let lastText = '';
    for await (const event of runner.runAsync({
      userId: 'user1',
      sessionId: session.id,
      newMessage: message,
    })) {
      const parts = event?.content?.parts;
      if (Array.isArray(parts)) {
        for (const part of parts) {
          if (typeof part?.text === 'string') lastText = part.text;
        }
      }
    }
    console.log('Response:', lastText?.slice(0, 500) || '(no response)');
  } catch (err: any) {
    console.log('Native path error (expected without GOOGLE_API_KEY):', err.message?.slice(0, 200));
  }
}

// ── Path 2: Agentspan ───────────────────────────────────────────────

async function runAgentspan() {
  console.log('\n=== Agentspan ===');
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
      agent,
      'Give me a recipe for classic Italian carbonara pasta.',
    );
    console.log(`Status: ${result.status}`);
    result.printResult();
  } catch (err: any) {
    console.log('Agentspan path error:', err.message?.slice(0, 200));
  } finally {
    await runtime.shutdown();
  }
}

// ── Run ──────────────────────────────────────────────────────────────

async function main() {
  await runNative();
  await runAgentspan();
}

main().catch(console.error);
