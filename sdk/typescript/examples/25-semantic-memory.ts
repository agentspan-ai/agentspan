/**
 * Semantic Memory -- long-term memory with similarity-based retrieval.
 *
 * Demonstrates `SemanticMemory` for persisting facts across sessions
 * and retrieving relevant context based on semantic similarity.
 *
 * The memory is injected into the agent's system prompt at runtime,
 * giving the agent access to relevant past knowledge.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import {
  Agent,
  AgentRuntime,
  tool,
  SemanticMemory,
  InMemoryStore,
} from '../src/index.js';
import { llmModel } from './settings.js';

// -- Build up a knowledge base ---------------------------------------------

const memory = new SemanticMemory({ store: new InMemoryStore() });

// Simulate storing facts from previous sessions
memory.add('The customer\'s name is Alice and she prefers email communication.');
memory.add('Alice\'s account is on the Enterprise plan since March 2021.');
memory.add('Last interaction: Alice reported a billing discrepancy on invoice #1042.');
memory.add('Alice\'s preferred language is English.');
memory.add('Company policy: Enterprise customers get priority support with 1-hour SLA.');
memory.add('Alice\'s timezone is US/Pacific.');

// -- Tool that uses memory for context -------------------------------------

const getCustomerContext = tool(
  async (args: { query: string }) => {
    const results = memory.search(args.query, 3);
    return results.map((r) => r.content).join('\n');
  },
  {
    name: 'get_customer_context',
    description: 'Retrieve relevant customer context from memory.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'The query to search memory for' },
      },
      required: ['query'],
    },
  },
);

// -- Agent with memory-backed context --------------------------------------

export const agent = new Agent({
  name: 'memory_agent',
  model: llmModel,
  tools: [getCustomerContext],
  instructions:
    'You are a customer support agent with access to a memory system. ' +
    'Use the get_customer_context tool to recall relevant information ' +
    'about the customer before responding. Always personalize your response.',
});

// -- Run -------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(agent);
    // await runtime.serve(agent);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    console.log('--- Query 1: Billing question ---');
    const result = await runtime.run(
    agent,
    'I have a question about my billing -- is there an issue with my account?',
    );
    result.printResult();

    console.log('\n--- Query 2: Plan question ---');
    const result2 = await runtime.run(
    agent,
    'What plan am I on and when did I sign up?',
    );
    result2.printResult();
  } finally {
    await runtime.shutdown();
    // }

    // // -- Direct memory operations ------------------------------------------------

    // console.log('\n--- Memory contents ---');
    // for (const entry of memory.listAll()) {
    // console.log(`  [${entry.id.slice(0, 8)}] ${entry.content}`);
    // }

    // console.log('\n--- Search for "billing" ---');
    // for (const entry of memory.search('billing invoice')) {
    // console.log(`  -> ${entry.content}`);
    // }
}

if (process.argv[1]?.endsWith('25-semantic-memory.ts') || process.argv[1]?.endsWith('25-semantic-memory.js')) {
  main().catch(console.error);
}
