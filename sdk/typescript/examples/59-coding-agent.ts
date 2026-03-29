/**
 * 59 - Coding Agent with QA Tester — write, review, and fix code.
 *
 * Demonstrates:
 *   - Swarm orchestration: agents decide when to hand off
 *   - Coder writes code, transfers to QA when ready
 *   - QA tester reviews and runs tests, transfers back if bugs found
 *   - Extended thinking for step-by-step reasoning
 *
 * Requirements:
 *   - Conductor server running
 *   - AGENTSPAN_SERVER_URL=http://localhost:8080/api as environment variable
 */

import { Agent, AgentRuntime } from '../src/index.js';

// -- QA Tester: reviews code and runs tests ----------------------------------

export const qaTester = new Agent({
  name: 'qa_tester',
  model: 'anthropic/claude-sonnet-4-20250514',
  instructions:
    'You are a meticulous QA engineer. Review the code written by the ' +
    'coder for correctness, edge cases, and bugs. Write and execute test ' +
    'cases that cover: normal inputs, edge cases (empty input, zero, ' +
    'negative numbers, large values), and boundary conditions.\n\n' +
    'If you find bugs, clearly describe them and transfer back to coder ' +
    'for fixes. If all tests pass, confirm the code is correct and ' +
    'provide your final QA report. Do NOT transfer back if all tests pass.',
  codeExecutionConfig: { enabled: true },
  thinkingBudgetTokens: 4096,
  maxTokens: 16384,
});

// -- Coder: writes code, hands off to QA for review --------------------------

export const coder = new Agent({
  name: 'coder',
  model: 'anthropic/claude-sonnet-4-20250514',
  instructions:
    'You are an expert Python developer. Write clean, well-structured ' +
    'Python code to solve the given problem. Always execute your code to ' +
    'verify it works. Always include ALL necessary code in each execution ' +
    '-- every code block runs in an isolated environment.\n\n' +
    'Once your code runs successfully, transfer to qa_tester for review. ' +
    'If the qa_tester reports bugs, fix them, re-run, and transfer back ' +
    'to qa_tester for verification.',
  codeExecutionConfig: { enabled: true },
  thinkingBudgetTokens: 4096,
  maxTokens: 16384,
  agents: [qaTester],
  strategy: 'swarm',
  maxTurns: 8,
  timeoutSeconds: 300,
});

// -- Run ---------------------------------------------------------------------

const prompt =
  'Write a Python function that finds all prime numbers up to N using ' +
  'the Sieve of Eratosthenes. Then use it to find all primes up to 100 ' +
  'and calculate their sum.';

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(coder);
    await runtime.serve(coder);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // console.log('='.repeat(60));
    // console.log('  Coding Agent + QA Tester (Swarm)');
    // console.log('  coder <-> qa_tester (LLM-driven handoffs)');
    // console.log('='.repeat(60));
    // console.log(`\nPrompt: ${prompt}\n`);
    // const runtime = new AgentRuntime();
    // try {
    // const result = await runtime.run(coder, prompt);

    // // Swarm output is a dict keyed by agent name
    // const output = result.output;
    // if (output && typeof output === 'object' && !Array.isArray(output)) {
    // for (const [agentName, text] of Object.entries(output as Record<string, string>)) {
    // console.log(`\n${'─'.repeat(60)}`);
    // console.log(`  [${agentName}]`);
    // console.log('─'.repeat(60));
    // console.log(text);
    // }
    // } else {
    // console.log(output);
    // }
  } finally {
    await runtime.shutdown();
    // }
}

if (process.argv[1]?.endsWith('59-coding-agent.ts') || process.argv[1]?.endsWith('59-coding-agent.js')) {
  main().catch(console.error);
}
