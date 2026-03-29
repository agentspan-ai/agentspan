/**
 * Loop Agent -- LoopAgent repeats sub-agents for iterative refinement.
 *
 * Demonstrates:
 *   - LoopAgent from @google/adk for iterative execution
 *   - SequentialAgent nested inside LoopAgent for write-critique cycles
 *   - maxIterations to control loop termination
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, SequentialAgent, LoopAgent } from '@google/adk';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// Writer drafts content
export const writer = new LlmAgent({
  name: 'draft_writer',
  model,
  instruction:
    'You are a writer. Write or revise a short haiku (3 lines: 5-7-5 syllables) ' +
    'about the given topic. If there is feedback from a previous critique in the conversation, ' +
    'incorporate it. Output only the haiku, nothing else.',
});

// Critic reviews and provides feedback
export const critic = new LlmAgent({
  name: 'critic',
  model,
  instruction:
    'You are a poetry critic. Review the haiku from the writer. ' +
    'Check: (1) Does it follow 5-7-5 syllable structure? ' +
    '(2) Is the imagery vivid? (3) Is there a seasonal or nature element? ' +
    'Provide 1-2 sentences of constructive feedback for improvement.',
});

// Each iteration: write -> critique
export const iteration = new SequentialAgent({
  name: 'write_critique_cycle',
  subAgents: [writer, critic],
});

// Loop the write-critique cycle 3 times
export const refinementLoop = new LoopAgent({
  name: 'refinement_loop',
  subAgents: [iteration],
  maxIterations: 3,
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(refinementLoop);
    await runtime.serve(refinementLoop);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(
    // refinementLoop,
    // 'Write a haiku about autumn leaves',
    // );
    // console.log('Status:', result.status);
    // result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('13-loop-agent.ts') || process.argv[1]?.endsWith('13-loop-agent.js')) {
  main().catch(console.error);
}
