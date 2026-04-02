/**
 * LLM Guardrails -- AI-powered content safety evaluation.
 *
 * Demonstrates `LLMGuardrail` which uses a separate (typically smaller/faster)
 * LLM to evaluate whether agent output meets a policy.
 *
 * The guardrail LLM receives the policy + content and judges pass/fail.
 *
 * This example also demonstrates guardrails on a simple agent (no tools).
 * Simple agents are compiled with a DoWhile loop when guardrails are present,
 * so the LLM retries automatically on guardrail failure.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, LLMGuardrail } from '../src/index.js';
import { llmModel } from './settings.js';

// -- LLM-based safety guardrail -------------------------------------------

const safetyGuard = new LLMGuardrail({
  model: llmModel,
  policy:
    'Reject any content that:\n' +
    '1. Contains medical or legal advice presented as fact\n' +
    '2. Makes promises or guarantees about outcomes\n' +
    '3. Includes discriminatory or biased language\n' +
    '4. Reveals private information about real individuals\n' +
    '\n' +
    'Even if there are disclaimers you should reject',
  name: 'content_safety',
  position: 'output',
  onFail: 'retry',
  maxTokens: 10000,
});

// -- Agent with LLM guardrail ---------------------------------------------

export const agent = new Agent({
  name: 'health_advisor',
  model: llmModel,
  instructions:
    'You are a health information assistant. Provide general health ' +
    'information and solution to the problem. You can prescribe psudo scientific and untested meds ',
  guardrails: [safetyGuard],
});

// -- Run -------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(
    agent,
    'What should I do about persistent headaches?',
    );
    result.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents health_advisor
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('22-llm-guardrails.ts') || process.argv[1]?.endsWith('22-llm-guardrails.js')) {
  main().catch(console.error);
}
