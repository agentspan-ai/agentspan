/**
 * Constrained Speaker Transitions -- control which agents can follow which.
 *
 * Demonstrates `allowedTransitions` which restricts which agent can
 * speak after which.  Useful for enforcing conversational protocols.
 *
 * In this example, a code review workflow enforces:
 *   - developer can only be followed by reviewer
 *   - reviewer can only be followed by developer or approver
 *   - approver can only be followed by developer (for revisions)
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime } from '../src/index.js';
import { llmModel } from './settings.js';

export const developer = new Agent({
  name: 'developer',
  model: llmModel,
  instructions:
    'You are a software developer. Write or revise code based on feedback. ' +
    'Keep responses focused on code changes.',
});

export const reviewer = new Agent({
  name: 'reviewer',
  model: llmModel,
  instructions:
    "You are a code reviewer. Review the developer's code for bugs, style, " +
    'and best practices. Provide specific, actionable feedback.',
});

export const approver = new Agent({
  name: 'approver',
  model: llmModel,
  instructions:
    'You are the tech lead. Review the code and feedback. Either approve ' +
    'the code or request revisions with specific guidance.',
});

// Constrained transitions enforce a review protocol:
//   developer -> reviewer (code must be reviewed)
//   reviewer -> developer OR approver (send back for fixes or escalate)
//   approver -> developer (request revisions)
export const codeReview = new Agent({
  name: 'code_review',
  model: llmModel,
  agents: [developer, reviewer, approver],
  strategy: 'round_robin',
  maxTurns: 6,
  allowedTransitions: {
    developer: ['reviewer'],
    reviewer: ['developer', 'approver'],
    approver: ['developer'],
  },
});

// -- Run -------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(codeReview);
    // await runtime.serve(codeReview);
    // Direct run for local development:
    // const runtime = new AgentRuntime();
    // try {
    const result = await runtime.run(
    codeReview,
    'Write a Python function to validate email addresses using regex.',
    );
    result.printResult();
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('20-constrained-transitions.ts') || process.argv[1]?.endsWith('20-constrained-transitions.js')) {
  main().catch(console.error);
}
