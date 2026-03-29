/**
 * Sequential Agent Pipeline -- SequentialAgent runs sub-agents in fixed order.
 *
 * Demonstrates:
 *   - SequentialAgent from @google/adk for pipeline orchestration
 *   - Each agent in the pipeline runs in order, outputs flowing to the next
 *   - researcher -> writer -> editor content pipeline
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, SequentialAgent } from '@google/adk';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// Step 1: Research agent gathers facts
export const researcher = new LlmAgent({
  name: 'researcher',
  model,
  instruction:
    'You are a research assistant. Given the user\'s topic, ' +
    'provide 3 key facts about it in a numbered list. Be concise.',
});

// Step 2: Writer agent takes the research and writes a summary
export const writer = new LlmAgent({
  name: 'writer',
  model,
  instruction:
    'You are a skilled writer. Take the research provided in the conversation ' +
    'and write a single engaging paragraph summarizing the key points. ' +
    'Keep it under 100 words.',
});

// Step 3: Editor agent polishes the summary
export const editor = new LlmAgent({
  name: 'editor',
  model,
  instruction:
    'You are an editor. Review the paragraph from the writer and improve it. ' +
    'Fix any issues with clarity, grammar, or flow. Output only the final polished paragraph.',
});

// Pipeline: researcher -> writer -> editor
export const pipeline = new SequentialAgent({
  name: 'content_pipeline',
  subAgents: [researcher, writer, editor],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(pipeline);
    await runtime.serve(pipeline);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(pipeline, 'The history of the Internet');
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('11-sequential-agent.ts') || process.argv[1]?.endsWith('11-sequential-agent.js')) {
  main().catch(console.error);
}
