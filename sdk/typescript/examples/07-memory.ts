/**
 * 07 - Memory
 *
 * Demonstrates ConversationMemory with maxMessages windowing,
 * and SemanticMemory with InMemoryStore for similarity search.
 */

import {
  Agent,
  AgentRuntime,
  ConversationMemory,
  SemanticMemory,
  InMemoryStore,
  tool,
} from '../src/index.js';

const MODEL = process.env.AGENTSPAN_LLM_MODEL ?? 'openai/gpt-4o';

// ── ConversationMemory ──────────────────────────────────

const conversationMem = new ConversationMemory({ maxMessages: 20 });

// Pre-populate with some context
conversationMem.addSystemMessage('You are a helpful research assistant.');
conversationMem.addUserMessage('I need help researching quantum computing.');
conversationMem.addAssistantMessage('I can help with that! What specific aspect?');

// ── SemanticMemory with InMemoryStore ───────────────────

const store = new InMemoryStore();
const semanticMem = new SemanticMemory({ store });

// Index some past articles
semanticMem.add('Quantum computing uses qubits instead of classical bits.');
semanticMem.add('Machine learning models can classify images with high accuracy.');
semanticMem.add('Quantum error correction is essential for practical quantum computers.');

// ── Tool that queries semantic memory ───────────────────

const recallTool = tool(
  async (args: { query: string }) => {
    const found = semanticMem.search(args.query, 3);
    return { results: found.map((e) => e.content) };
  },
  {
    name: 'recall_articles',
    description: 'Search past articles by topic.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Search query' },
      },
      required: ['query'],
    },
  },
);

// ── Agent with memory ───────────────────────────────────

export const researchAgent = new Agent({
  name: 'research_agent',
  model: MODEL,
  instructions: 'Use your memory and recall tool to answer questions.',
  tools: [recallTool],
  memory: conversationMem,
});

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(researchAgent);
    // await runtime.serve(researchAgent);
    // Direct run for local development:
    const result = await runtime.run(
    researchAgent,
    'What do we know about quantum error correction?',
    );
    result.printResult();
    // await runtime.shutdown();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('07-memory.ts') || process.argv[1]?.endsWith('07-memory.js')) {
  console.log('Conversation messages:', conversationMem.toChatMessages().length);

  const results = semanticMem.search('quantum error', 2);
  console.log('\nSemantic search results:');
  for (const entry of results) {
    console.log(`  - ${entry.content}`);
  }

  main().catch(console.error);
}
