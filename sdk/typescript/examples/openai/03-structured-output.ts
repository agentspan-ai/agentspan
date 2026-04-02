// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

/**
 * OpenAI Agent with Structured Output -- enforced JSON schema response.
 *
 * Demonstrates:
 *   - Using outputType with a zod schema for structured responses
 *   - The agent is forced to return data matching the schema
 *   - Model settings (temperature) for deterministic output
 *
 * Requirements:
 *   - AGENTSPAN_SERVER_URL for the Agentspan path
 */

import { Agent, setTracingDisabled } from '@openai/agents';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

setTracingDisabled(true);

// ── Structured output schema ────────────────────────────────────────

const MovieRecommendation = z.object({
  title: z.string(),
  year: z.number(),
  genre: z.string(),
  reason: z.string(),
});

const MovieList = z.object({
  recommendations: z.array(MovieRecommendation),
  theme: z.string(),
});

// ── Agent ───────────────────────────────────────────────────────────

export const agent = new Agent({
  name: 'movie_recommender',
  instructions:
    'You are a movie recommendation expert. When asked for movie suggestions, ' +
    'return a structured list of recommendations with title, year, genre, ' +
    'and a brief reason for each recommendation. Identify the overall theme.',
  model: 'gpt-4o-mini',
  outputType: MovieList,
  modelSettings: {
    temperature: 0.3,
    maxTokens: 1000,
  },
});

const prompt = 'Recommend 3 sci-fi movies that explore the concept of artificial intelligence.';

// ── Run on agentspan ──────────────────────────────────────────────
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, prompt);
    console.log('Status:', result.status);
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples/openai --agents movie_recommender
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
