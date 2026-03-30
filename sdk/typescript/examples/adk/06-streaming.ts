/**
 * Google ADK Agent with Streaming -- real-time event streaming.
 *
 * Demonstrates:
 *   - Streaming events from a Google ADK agent
 *   - Agentspan path: runtime.stream() with event types
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, FunctionTool } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Tool ─────────────────────────────────────────────────────────────

const searchDocumentation = new FunctionTool({
  name: 'search_documentation',
  description: 'Search the product documentation.',
  parameters: z.object({
    query: z.string().describe('Search query string'),
  }),
  execute: async (args: { query: string }) => {
    const docs: Record<string, { title: string; content: string }> = {
      installation: {
        title: 'Installation Guide',
        content: 'Run `npm install mypackage`. Requires Node.js 18+.',
      },
      authentication: {
        title: 'Authentication',
        content: 'Use API keys via the X-API-Key header. Keys are managed in the dashboard.',
      },
      'rate limits': {
        title: 'Rate Limiting',
        content: 'Free tier: 100 req/min. Pro: 1000 req/min. Enterprise: unlimited.',
      },
    };
    for (const [key, value] of Object.entries(docs)) {
      if (args.query.toLowerCase().includes(key)) {
        return { found: true, ...value };
      }
    }
    return { found: false, message: 'No matching documentation found.' };
  },
});

// ── Agent ────────────────────────────────────────────────────────────

export const agent = new LlmAgent({
  name: 'docs_assistant',
  model,
  instruction:
    'You are a documentation assistant. Use the search tool to find ' +
    'relevant docs and provide clear, well-formatted answers.',
  tools: [searchDocumentation],
});

// ── Run on agentspan (streaming) ───────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(agent);
    await runtime.serve(agent);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const streamHandle = await runtime.stream(
    // agent,
    // 'How do I authenticate with the API?',
    // );
    // console.log(`Execution started: ${streamHandle.executionId}\n`);
    // console.log('Events:');

    // for await (const event of streamHandle) {
    // switch (event.type) {
    // case 'thinking':
    // console.log(`  [thinking] ${event.content}`);
    // break;
    // case 'tool_call':
    // console.log(`  [tool_call] ${event.toolName}(${JSON.stringify(event.args)})`);
    // break;
    // case 'tool_result':
    // console.log(`  [tool_result] ${event.toolName} -> ${JSON.stringify(event.result).slice(0, 100)}`);
    // break;
    // case 'done':
    // console.log(`  [done] ${JSON.stringify(event.output).slice(0, 200)}`);
    // break;
    // case 'error':
    // console.log(`  [error] ${event.content}`);
    // break;
    // }
    // }

    // const final = await streamHandle.getResult();
    // console.log(`\nStatus: ${final.status}`);
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('06-streaming.ts') || process.argv[1]?.endsWith('06-streaming.js')) {
  main().catch(console.error);
}
