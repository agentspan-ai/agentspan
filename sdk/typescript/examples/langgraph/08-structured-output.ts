/**
 * Structured Output -- createReactAgent with responseFormat for typed data.
 *
 * Demonstrates:
 *   - Using responseFormat on createReactAgent for typed JSON responses
 *   - Defining a Zod schema for the expected output shape
 *   - Parsing and accessing structured fields from the result
 */

import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Structured output schema
// ---------------------------------------------------------------------------
const MovieReviewSchema = z.object({
  title: z.string().describe('The movie title'),
  rating: z.number().describe('Rating out of 10'),
  pros: z.array(z.string()).describe('List of positive aspects'),
  cons: z.array(z.string()).describe('List of negative aspects'),
  summary: z.string().describe('A brief summary of the review'),
  recommended: z.boolean().describe('Whether the movie is recommended'),
});

// ---------------------------------------------------------------------------
// Build the graph with structured output
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
const graph = createReactAgent({
  llm,
  tools: [],
  responseFormat: MovieReviewSchema,
});

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

const PROMPT = 'Write a review for the movie Inception (2010).';

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(graph, PROMPT);
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
