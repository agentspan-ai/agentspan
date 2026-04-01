// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

/**
 * OpenAI Agent with Model Settings -- temperature, max tokens, and more.
 *
 * Demonstrates:
 *   - Configuring model settings for fine-tuned LLM behavior
 *   - Low temperature for deterministic responses
 *   - High temperature for creative responses
 *
 * Requirements:
 *   - AGENTSPAN_SERVER_URL for the Agentspan path
 */

import { Agent, setTracingDisabled } from '@openai/agents';
import { AgentRuntime } from '../../src/index.js';

setTracingDisabled(true);

// ── Creative agent with high temperature ────────────────────────────

export const creativeAgent = new Agent({
  name: 'creative_writer',
  instructions:
    'You are a creative writing assistant. Write with vivid imagery ' +
    'and unexpected metaphors. Be bold and imaginative.',
  model: 'gpt-4o-mini',
  modelSettings: {
    temperature: 0.9,
    maxTokens: 500,
  },
});

// ── Precise agent with low temperature ──────────────────────────────

export const preciseAgent = new Agent({
  name: 'code_reviewer',
  instructions:
    'You are a precise code reviewer. Analyze code snippets for bugs, ' +
    'security issues, and best practices. Be concise and specific.',
  model: 'gpt-4o-mini',
  modelSettings: {
    temperature: 0.1,
    maxTokens: 300,
  },
});

// ── Run on agentspan ──────────────────────────────────────────────
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(creativeAgent);
    // await runtime.serve(creativeAgent);
    // Direct run for local development:
    console.log('--- Creative Agent (temp=0.9) ---');
    const creativeResult = await runtime.run(
    creativeAgent,
    'Write a two-sentence story about a robot learning to paint.',
    );
    console.log('Status:', creativeResult.status);
    creativeResult.printResult();

    console.log('\n--- Precise Agent (temp=0.1) ---');
    const preciseResult = await runtime.run(
    preciseAgent,
    'Review this Python code: `data = eval(user_input)`',
    );
    console.log('Status:', preciseResult.status);
    preciseResult.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('06-model-settings.ts') || process.argv[1]?.endsWith('06-model-settings.js')) {
  main().catch(console.error);
}
