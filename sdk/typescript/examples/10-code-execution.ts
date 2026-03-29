/**
 * 10 - Code Execution
 *
 * Demonstrates LocalCodeExecutor.asTool() attached to an agent.
 * The agent can execute code to answer questions.
 */

import {
  Agent,
  AgentRuntime,
  LocalCodeExecutor,
} from '../src/index.js';

const MODEL = process.env.AGENTSPAN_LLM_MODEL ?? 'openai/gpt-4o';

// -- Create a local code executor --
const executor = new LocalCodeExecutor({ timeout: 10 });

// -- Wrap as a tool --
const codeTool = executor.asTool('run_code');

// -- Agent with code execution --
export const codeAgent = new Agent({
  name: 'code_agent',
  model: MODEL,
  instructions:
    'You can execute code to solve problems. ' +
    'Use the run_code tool to execute JavaScript code.',
  tools: [codeTool],
  codeExecutionConfig: {
    enabled: true,
    allowedLanguages: ['javascript', 'python'],
    timeout: 10,
  },
});

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    await runtime.deploy(codeAgent);
    await runtime.serve(codeAgent);

    // Quick test: uncomment below (and comment out serve) to run directly.
    // const result = await runtime.run(
    // codeAgent,
    // 'Calculate the first 10 Fibonacci numbers using code.',
    // );
    // result.printResult();
    // await runtime.shutdown();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('10-code-execution.ts') || process.argv[1]?.endsWith('10-code-execution.js')) {
  // Test executor directly
  const directResult = executor.execute('console.log("Hello from code executor!")', 'javascript');
  console.log('Direct execution:', directResult.output);
  console.log('Success:', directResult.success);

  main().catch(console.error);
}
