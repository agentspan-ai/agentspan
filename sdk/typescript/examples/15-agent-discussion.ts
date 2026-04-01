/**
 * Agent Discussion -- durable round-robin debate compiled to a Conductor DoWhile loop.
 *
 * Demonstrates a multi-turn discussion between agents with opposing
 * viewpoints using the round_robin strategy. The entire debate runs
 * server-side as a Conductor DoWhile loop -- durable, restartable, and
 * observable in the Conductor UI. After the discussion, a summary agent
 * distills the transcript into a balanced conclusion via the .pipe()
 * pipeline operator.
 *
 * Flow (all server-side):
 *   DoWhile(6 turns):
 *     turn 0 -> optimist
 *     turn 1 -> skeptic
 *     turn 2 -> optimist
 *     ...
 *   summarizer produces conclusion
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Discussion participants --------------------------------------------------

export const optimist = new Agent({
  name: 'optimist',
  model: llmModel,
  instructions:
    'You are an optimistic technologist debating a topic. ' +
    'Argue FOR the topic. Keep your response to 2-3 concise paragraphs. ' +
    "Acknowledge the other side's points before making your case.",
});

export const skeptic = new Agent({
  name: 'skeptic',
  model: llmModel,
  instructions:
    'You are a thoughtful skeptic debating a topic. ' +
    'Raise concerns and argue AGAINST the topic. ' +
    'Keep your response to 2-3 concise paragraphs. ' +
    "Acknowledge the other side's points before making your case.",
});

export const summarizer = new Agent({
  name: 'summarizer',
  model: llmModel,
  instructions:
    'You are a neutral moderator. You have just observed a debate ' +
    'between an optimist and a skeptic. Summarize the key arguments ' +
    'from both sides and provide a balanced conclusion. ' +
    'Structure your response with: Key Arguments For, ' +
    'Key Arguments Against, and Balanced Conclusion.',
});

// -- Round-robin discussion: 6 turns (3 rounds of back-and-forth) -------------

export const discussion = new Agent({
  name: 'discussion',
  model: llmModel,
  agents: [optimist, skeptic],
  strategy: 'round_robin',
  maxTurns: 6,
});

// Pipe discussion transcript to summarizer
const pipeline = discussion.pipe(summarizer);

// -- Run ----------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(pipeline);
    // await runtime.serve(pipeline);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    const result = await runtime.run(
    pipeline,
    'Should AI agents be allowed to autonomously make financial decisions for individuals?',
    );
    result.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('15-agent-discussion.ts') || process.argv[1]?.endsWith('15-agent-discussion.js')) {
  main().catch(console.error);
}
