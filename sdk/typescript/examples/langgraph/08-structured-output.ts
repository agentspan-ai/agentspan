/**
 * Structured Output -- createReactAgent with withStructuredOutput for typed data.
 *
 * Demonstrates:
 *   - Using withStructuredOutput on the LLM for typed JSON responses
 *   - Defining a Zod schema for the expected output shape
 *   - Parsing and accessing structured fields from the result
 */

import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage } from '@langchain/core/messages';
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

const PROMPT = 'Write a review for the movie Inception (2010).';

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
async function main() {
  // ── Path 1: Native ──
  console.log('=== Native LangGraph execution ===');
  const nativeResult = await graph.invoke({
    messages: [new HumanMessage(PROMPT)],
  });

  // With responseFormat, the last message contains structured output
  // and structuredResponse holds the parsed object
  if (nativeResult.structuredResponse) {
    const review = nativeResult.structuredResponse;
    console.log('Title:', review.title);
    console.log('Rating:', review.rating, '/ 10');
    console.log('Pros:');
    for (const pro of review.pros) console.log('  +', pro);
    console.log('Cons:');
    for (const con of review.cons) console.log('  -', con);
    console.log('Summary:', review.summary);
    console.log('Recommended:', review.recommended);
  } else {
    // Fallback: print last message
    const lastMsg = nativeResult.messages[nativeResult.messages.length - 1];
    console.log('Response:', lastMsg.content);
  }

  // ── Path 2: Agentspan ──
  console.log('\n=== Agentspan passthrough execution ===');
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
