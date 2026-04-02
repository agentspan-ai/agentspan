/**
 * 39 - Local Code Execution
 *
 * Demonstrates three ways to enable code execution on an agent:
 *   1. Simple config: codeExecutionConfig with enabled=true
 *   2. With restrictions: allowedLanguages + allowedCommands
 *   3. Full config: CodeExecutionConfig + LocalCodeExecutor.asTool()
 *
 * When codeExecutionConfig is set, the agent automatically gets an
 * execute_code tool. The LLM calls it via native function calling --
 * no manual executor setup needed.
 *
 * Requirements:
 *   - Conductor server with LLM support
 *   - AGENTSPAN_SERVER_URL=http://localhost:6767/api as environment variable
 *   - AGENTSPAN_LLM_MODEL=openai/gpt-4o-mini as environment variable
 */

import { Agent, AgentRuntime, LocalCodeExecutor } from '../src/index.js';
import { llmModel } from './settings.js';

// -- Example 1: Simple flag --------------------------------------------------
// Just set codeExecutionConfig with enabled: true

export const simpleCoder = new Agent({
  name: 'simple_coder',
  model: llmModel,
  codeExecutionConfig: {
    enabled: true,
  },
  instructions: 'You are a Python developer. Write and execute code to solve problems.',
});

// -- Example 2: With restrictions --------------------------------------------
// Allow Python + Bash, but only permit pip and ls commands.

export const restrictedCoder = new Agent({
  name: 'restricted_coder',
  model: llmModel,
  codeExecutionConfig: {
    enabled: true,
    allowedLanguages: ['python', 'bash'],
    allowedCommands: ['pip', 'ls', 'cat', 'git'],
  },
  instructions:
    'You are a developer with restricted shell access. ' +
    'You can write Python and Bash code, but only use ' +
    'pip, ls, cat, and git commands.',
});

// -- Example 3: Full CodeExecutionConfig with LocalCodeExecutor ---------------

const executor = new LocalCodeExecutor({ timeout: 60 });
const codeTool = executor.asTool('execute_code');

export const configCoder = new Agent({
  name: 'config_coder',
  model: llmModel,
  tools: [codeTool],
  codeExecutionConfig: {
    enabled: true,
    allowedLanguages: ['python'],
    allowedCommands: ['pip'],
    timeout: 60,
  },
  instructions: 'You are a Python developer with a 60s timeout and pip access only.',
});

// -- Run ---------------------------------------------------------------------

// Only run when executed directly (not when imported for discovery)
async function main() {
  const runtime = new AgentRuntime();
  try {
    console.log('--- Simple Code Execution ---');
    const result1 = await runtime.run(
    simpleCoder,
    'Write a Python function to find the first 10 prime numbers and print them.',
    );
    result1.printResult();

    console.log('\n--- Restricted Code Execution ---');
    const result2 = await runtime.run(
    restrictedCoder,
    'List the files in the current directory using bash.',
    );
    result2.printResult();

    // Production pattern:
    // 1. Deploy once during CI/CD:
    // await runtime.deploy(simpleCoder);
    // CLI alternative:
    // agentspan deploy --package sdk/typescript/examples --agents simple_coder
    //
    // 2. In a separate long-lived worker process:
    // await runtime.serve(simpleCoder);
  } finally {
    await runtime.shutdown();
  }
}

if (process.argv[1]?.endsWith('39-local-code-execution.ts') || process.argv[1]?.endsWith('39-local-code-execution.js')) {
  main().catch(console.error);
}
