/**
 * 36 - Simple Agent Guardrails
 *
 * Demonstrates guardrails on a simple agent (no tools, no sub-agents).
 * The agent is compiled with a DoWhile loop that retries the LLM call when
 * a guardrail fails -- same durable retry behavior as tool-using agents.
 *
 * This example uses mixed guardrail types:
 *   - RegexGuardrail: compiled as a Conductor InlineTask (server-side JS)
 *   - Custom guardrail function: compiled as a Conductor worker task
 *
 * Both guardrails run inside the same DoWhile loop. If either fails with
 * onFail="retry", the feedback message is appended to the conversation
 * and the LLM tries again.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, RegexGuardrail, guardrail } from '../src/index.js';
import type { GuardrailResult } from '../src/index.js';
import { llmModel } from './settings.js';

// -- RegexGuardrail: block bullet-point lists --------------------------------
// Compiles as an InlineTask -- runs entirely on the Conductor server.

const noBulletLists = new RegexGuardrail({
  name: 'no_lists',
  patterns: [String.raw`^\s*[-*]\s`, String.raw`^\s*\d+\.\s`],
  mode: 'block',
  position: 'output',
  onFail: 'retry',
  message:
    'Do not use bullet points or numbered lists. ' +
    'Write in flowing prose paragraphs instead.',
});

// -- Custom guardrail: enforce minimum length --------------------------------
// Compiles as a Conductor worker task (TypeScript function).

const minLength = guardrail(
  (content: string): GuardrailResult => {
    const wordCount = content.split(/\s+/).filter(Boolean).length;
    if (wordCount < 50) {
      return {
        passed: false,
        message:
          `Response is too short (${wordCount} words). ` +
          'Please provide a more detailed answer with at least 50 words.',
      };
    }
    return { passed: true };
  },
  {
    name: 'min_length',
    position: 'output',
    onFail: 'retry',
  },
);

// -- Agent (no tools) --------------------------------------------------------

export const agent = new Agent({
  name: 'essay_writer',
  model: llmModel,
  instructions:
    'You are a concise essay writer. Answer the user\'s question in ' +
    'well-structured prose paragraphs. Do NOT use bullet points or ' +
    'numbered lists.',
  guardrails: [noBulletLists.toGuardrailDef(), minLength],
});

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    const result = await runtime.run(agent, 'Explain why the sky is blue.');
    result.printResult();

    // Verify guardrails
    const output = String(result.output);
    const hasBullets = output
    // .split('\n')
    // .some((line) => line.trim().startsWith('-') || line.trim().startsWith('*'));
    const wordCount = output.split(/\s+/).filter(Boolean).length;

    if (hasBullets) {
    console.log('[WARN] Output contains bullet points -- guardrail may not have fired');
    } else if (wordCount < 50) {
    console.log(`[WARN] Output too short (${wordCount} words)`);
    } else {
    console.log(`[OK] Prose response, ${wordCount} words -- guardrails passed`);
    }

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(agent);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents essay_writer
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(agent);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('36-simple-agent-guardrails.ts') || process.argv[1]?.endsWith('36-simple-agent-guardrails.js')) {
  main().catch(console.error);
}
