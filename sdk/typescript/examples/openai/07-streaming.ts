// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

/**
 * OpenAI Agent with Streaming -- real-time event streaming.
 *
 * Demonstrates:
 *   - An OpenAI agent with tools
 *   - Running via Agentspan passthrough
 *
 * Requirements:
 *   - AGENTSPAN_SERVER_URL for the Agentspan path
 */

import {
  Agent,
  tool,
  setTracingDisabled,
} from '@openai/agents';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

setTracingDisabled(true);

// ── Tool ────────────────────────────────────────────────────────────

const searchKnowledgeBase = tool({
  name: 'search_knowledge_base',
  description: 'Search the knowledge base for relevant information.',
  parameters: z.object({ query: z.string().describe('Search query') }),
  execute: async ({ query }) => {
    const knowledge: Record<string, string> = {
      'return policy':
        'Returns accepted within 30 days with receipt. Electronics have a 15-day return window.',
      shipping:
        'Free shipping on orders over $50. Standard delivery: 3-5 business days.',
      warranty:
        'All products come with a 1-year manufacturer warranty. Extended warranty available for electronics.',
    };
    const queryLower = query.toLowerCase();
    for (const [key, value] of Object.entries(knowledge)) {
      if (queryLower.includes(key)) return value;
    }
    return 'No relevant information found for your query.';
  },
});

// ── Agent ───────────────────────────────────────────────────────────

const agent = new Agent({
  name: 'support_agent',
  instructions:
    'You are a customer support agent. Use the knowledge base to answer ' +
    'questions accurately. If you cannot find the answer, say so honestly.',
  model: 'gpt-4o-mini',
  tools: [searchKnowledgeBase],
});

const prompt = "What's your return policy for electronics?";

// ── Run on agentspan ──────────────────────────────────────────────
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, prompt);
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
