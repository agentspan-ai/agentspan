/**
 * 49 - Include Contents — control context passed to sub-agents.
 *
 * When `includeContents: 'none'`, a sub-agent starts with a clean slate
 * and does NOT see the parent agent's conversation history.
 *
 * Requirements:
 *   - Conductor server with include_contents support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { z } from 'zod';
import { Agent, AgentRuntime, tool } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Tool --------------------------------------------------------------------

const summarizeText = tool(
  async (args: { text: string }) => {
    const words = args.text.split(/\s+/);
    return { summary: words.slice(0, 20).join(' ') + '...', word_count: words.length };
  },
  {
    name: 'summarize_text',
    description: 'Summarize a piece of text.',
    inputSchema: z.object({
      text: z.string().describe('The text to summarize'),
    }),
  },
);

// -- Agents ------------------------------------------------------------------

// This sub-agent won't see the parent's conversation history
export const independentSummarizer = new Agent({
  name: 'independent_summarizer_49',
  model: llmModel,
  instructions: 'You are a summarizer. Summarize any text given to you concisely.',
  tools: [summarizeText],
  includeContents: 'none', // No parent context
});

// This sub-agent WILL see the parent's conversation history (default)
export const contextAwareHelper = new Agent({
  name: 'context_aware_helper_49',
  model: llmModel,
  instructions: 'You are a helpful assistant that builds on prior conversation context.',
});

export const coordinator = new Agent({
  name: 'coordinator_49',
  model: llmModel,
  instructions:
    'You coordinate tasks. Route summarization requests to ' +
    'independent_summarizer_49 and general questions to context_aware_helper_49.',
  agents: [independentSummarizer, contextAwareHelper],
  strategy: 'handoff',
});

// -- Run ---------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(coordinator);
    // await runtime.serve(coordinator);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    const result = await runtime.run(
    coordinator,
    "Please summarize this: 'The quick brown fox jumps over the lazy dog. " +
    "This sentence contains every letter of the alphabet and is commonly " +
    "used for typography testing.'",
    );
    result.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('49-include-contents.ts') || process.argv[1]?.endsWith('49-include-contents.js')) {
  main().catch(console.error);
}
