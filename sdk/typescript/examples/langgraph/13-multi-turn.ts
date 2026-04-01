/**
 * Multi-Turn Conversation -- MemorySaver + sessionId for continuity.
 *
 * Demonstrates:
 *   - Using MemorySaver checkpointer for persistent conversation history
 *   - Passing sessionId to runtime.run for scoped memory
 *   - How different session IDs maintain separate conversation threads
 *   - A practical use case: interview preparation assistant
 */

import { MemorySaver } from '@langchain/langgraph';
import { createReactAgent } from '@langchain/langgraph/prebuilt';
import { ChatOpenAI } from '@langchain/openai';
import { AgentRuntime } from '../../src/index.js';

// ---------------------------------------------------------------------------
// Build the graph with checkpointer
// ---------------------------------------------------------------------------
const llm = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
const checkpointer = new MemorySaver();
const graph = createReactAgent({
  llm,
  tools: [],
  checkpointer,
  prompt:
    'You are an interview preparation coach. ' +
    'Remember what the user tells you about their background, skills, and target role. ' +
    'Build on previous messages to give increasingly personalized advice.',
});

// Add agentspan metadata for extraction
(graph as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langgraph',
};

// ---------------------------------------------------------------------------
// Run on agentspan
// ---------------------------------------------------------------------------
async function main() {
  const SESSION_A = 'candidate-alice';
  const SESSION_B = 'candidate-bob';

  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(graph);
    // await runtime.serve(graph);
    // Direct run for local development:
    console.log("=== Alice's session ===");
    let result = await runtime.run(
    graph,
    "I'm applying for a senior backend engineer role at a fintech startup. " +
    'I have 5 years of Python experience.',
    { sessionId: SESSION_A },
    );
    result.printResult();

    console.log("\n=== Bob's session (separate memory) ===");
    result = await runtime.run(
    graph,
    'I want to become a product manager. I have a marketing background.',
    { sessionId: SESSION_B },
    );
    result.printResult();

    console.log("\n=== Alice's session — follow-up (remembers context) ===");
    result = await runtime.run(
    graph,
    'What technical topics should I review for my upcoming interviews?',
    { sessionId: SESSION_A },
    );
    result.printResult();

    console.log("\n=== Bob's session — follow-up (remembers context) ===");
    result = await runtime.run(
    graph,
    'What skills gap should I address first?',
    { sessionId: SESSION_B },
    );
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('13-multi-turn.ts') || process.argv[1]?.endsWith('13-multi-turn.js')) {
  main().catch(console.error);
}
